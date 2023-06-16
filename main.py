from flask import Flask, render_template, request, redirect, url_for, flash

from config import *

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

from sqlalchemy.orm import relationship
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user
from sqlalchemy import Column, Integer, ForeignKey

import stripe
import os

count = 0
Success = None
Enter = False
app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get('SECRET_KEY')
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"
app.config["SQLALCHEMY_BINDS"] = {'items': "sqlite:///items.db"}
app.config["TRACK_MODIFICATIONS"] = False


stripe.api_key = STRIPE_SECRET_KEY

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), nullable=False, unique=True)
    password = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    phone_no = db.Column(db.String(20))
    address = db.Column(db.String(500))
    cart_item_count = db.Column(db.Integer, default=0)
    cart = relationship("Items", back_populates="user")


class Items(db.Model):
    __tablename__ = "cart"
    id = db.Column(db.Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey('users.id'))
    item_name = db.Column(db.String(500))
    item_price = db.Column(db.Integer)
    user = relationship("User", back_populates="cart")
    item_rating = db.Column(db.Integer, default=0)
    img_url = db.Column(db.String(1000))
    desc = db.Column(db.String(1000))
    price_id = db.Column(db.String(100))
    quantity = db.Column(db.Integer, default=1)


class Things(db.Model):
    __bind_key__ = 'items'
    id = db.Column(db.Integer, primary_key=True)
    Name = db.Column(db.String(100), nullable=False)
    Price = db.Column(db.Integer, nullable=False)
    Rating = db.Column(db.Integer)
    img_url = db.Column(db.String(1000))
    desc = db.Column(db.String(1000))
    price_id = db.Column(db.String(100))

with app.app_context():
    db.create_all()

@app.route('/')
def home():
    global Success
    Success = None
    if current_user.is_authenticated:
        count = current_user.cart_item_count
    else:
        count = 0
    things = db.session.query(Things).all()
    return render_template('index.html', things=things, count=count)


@app.route('/login', methods=['POST', 'GET'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        user = User.query.filter_by(email=email).first()
        if user:
            if check_password_hash(user.password, password):
                login_user(user)
                return redirect(url_for('home'))
            else:
                flash("Wrong password")
        else:
            flash("This email does not exist")
    return render_template("login.html")



@app.route('/register', methods=['POST', 'GET'])
def register():
    if request.method == 'POST':
        if User.query.filter_by(email=request.form['email']).first():
            flash("Email already exists, login")
            return redirect(url_for("login"))

        hash_and_salted = generate_password_hash(request.form["password"], method='pbkdf2:sha256', salt_length=8)

        new_user = User()


        new_user.email = request.form["email"]
        new_user.name = request.form["name"]
        new_user.password = hash_and_salted

        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for("home"))
    return render_template("register.html")


@app.route('/product')
def product():
    id = request.args.get('id')
    item = db.session.query(Things).get(id)
    return render_template('products.html', item=item, count=current_user.cart_item_count)


@app.route('/add_to_cart', methods=['GET', 'POST'])
def add_to_cart():
    global cart_item_count
    quantity = request.form.get('quantity')
    item_id = request.args.get('id')
    item = db.session.query(Things).get(item_id)
    if current_user.is_authenticated:
        new_item = Items()
        new_item.item_id = current_user.id
        new_item.item_name = item.Name
        new_item.item_price = item.Price
        new_item.item_rating = item.Rating
        new_item.img_url = item.img_url
        new_item.price_id = item.price_id
        new_item.quantity = quantity
        current_user.cart_item_count += 1
        db.session.add(new_item)
        db.session.commit()


    return redirect(url_for('home'))


@app.route('/cart')
def cart():
    total = 5
    items = db.session.query(Items).all()
    for i in items:
        if i.item_id == current_user.id:
            total += i.item_price

    return render_template('cart.html', id=current_user.id, items=items, price=total, success=Success, enter=Enter, count=current_user.cart_item_count)


@app.route('/checkout', methods=['POST'])
def create_checkout_session():
    global Success
    try:
        item_to_del = db.session.query(Items).all()
        checkout_session = stripe.checkout.Session.create(
            line_items=[
                {
                    # Provide the exact Price ID (for example, pr_1234) of the product you want to sell
                    'price': i.price_id,
                    'quantity': i.quantity,
                } for i in item_to_del if i.item_id == current_user.id
            ],
            mode='payment',
            success_url=url_for('cart', _external=True),
            cancel_url=url_for('cart', _external=True),
        )
        Success = True
        for i in item_to_del:
            if i.item_id == current_user.id:
                current_user.cart_item_count = 0
                db.session.delete(i)
                db.session.commit()
    except Exception as e:
        Success = False
        return str(e)


    return redirect(checkout_session.url)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('home'))


@app.route('/remove')
def remove():
    current_user.cart_item_count -= 1
    item_id = request.args.get('id')
    item_to_del = db.session.query(Items).get(item_id)
    db.session.delete(item_to_del)
    db.session.commit()
    return redirect(url_for('cart'))

@app.route('/add_address')
def addresses():
    global Enter
    Enter = True
    return redirect(url_for('cart'))

@app.route('/get_address', methods=['POST', 'GET'])
def get():
    global Enter
    if request.method == 'POST':
        address = request.form.get('address')
        current_user.address = address
        db.session.commit()
        Enter = False
        return redirect(url_for('cart'))


if __name__ == ('__main__'):
    app.run(debug=True)