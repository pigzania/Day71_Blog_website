from datetime import date
from flask import Flask, abort, render_template, redirect, url_for, flash, request
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
from flask_gravatar import Gravatar
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user, login_required
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Text, ForeignKey
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
# Import your forms from the forms.py
from forms import CreatePostForm, RegisterForm, LoginForm, CommentForm
from typing import List
from load_dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY")
ckeditor = CKEditor(app)
Bootstrap5(app)


login_manager = LoginManager()
login_manager.init_app(app)

# Flask-Gravartar
gravatar = Gravatar(app, size=100, rating='x', default='retro', force_default=False, force_lower=False, use_ssl=False,
                    base_url=None)

# CREATE DATABASE
class Base(DeclarativeBase):
    pass


app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DB_URI", "sqlite:///posts.db")
db = SQLAlchemy(model_class=Base)
db.init_app(app)


# CONFIGURE TABLES
class User(UserMixin, db.Model):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(250), nullable=False)
    email: Mapped[str] = mapped_column(String(250), nullable=False, unique=True)
    password: Mapped[str] = mapped_column(String(1000), nullable=False)
    # This will act like a List of BlogPost objects attached to each User.
    # The "author" refers to the author property in the BlogPost class.
    posts = relationship("BlogPost", back_populates="author")
    comments = relationship("Comment", back_populates="author")

# TODO: Create a User table for all your registered users.
class BlogPost(db.Model):
    __tablename__ = "blog_posts"
    # Create Foreign Key, "users.id" the users refers to the tablename of User.
    author_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("users.id"))
    # Create reference to the User object. The "posts" refers to the posts property in the User class.
    author = relationship("User", back_populates="posts")
    post_comments = relationship("Comment", back_populates="parent_post")
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    subtitle: Mapped[str] = mapped_column(String(250), nullable=False)
    date: Mapped[str] = mapped_column(String(250), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    img_url: Mapped[str] = mapped_column(String(250), nullable=False)


class Comment(db.Model):
    __tablename__ = "comments"
    author_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("users.id"))
    author = relationship("User", back_populates="comments")
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(String(1000), nullable=False)     # Change 1: From String() to Text
    parent_post = relationship("BlogPost", back_populates="post_comments")
    post_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("blog_posts.id"))  # Change 2: from Mapped[int] to str

with app.app_context():
    db.create_all()


def admin_only(function):
    @wraps(function)
    def wrapper():
        if current_user.is_authenticated:        # prevent -> AttributeError: 'AnonymousUserMixin' object has no attribute 'id'
            if current_user.id == 1:
                return function()
        else:
            return abort(403)
    return wrapper


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# TODO: Use Werkzeug to hash the user's password when creating a new user.
@app.route('/register', methods=["GET", "POST"])
def register():
    register_form = RegisterForm()
    if register_form.validate_on_submit():
        is_user_registered = db.session.execute(db.select(User).where(User.email == register_form.email.data)).scalar()
        # This does not return None even if nothing in the database matches with it, must put .scalar()
        if not is_user_registered:
            hashed_pw = generate_password_hash(register_form.password.data, method="pbkdf2:sha256", salt_length=8)
            new_user = User(name=register_form.name.data, email=register_form.email.data, password=hashed_pw)
            db.session.add(new_user)
            db.session.commit()
            login_user(new_user)
            return redirect(url_for("get_all_posts"))
        else:
            return redirect(url_for("login", has_registered=True))

    return render_template("register.html", form=register_form, logged_in=current_user.is_authenticated)


# TODO: Retrieve a user from the database based on their email. 
@app.route('/login', methods=["POST", "GET"])
def login():
    has_registered = request.args.get("has_registered", False)          # gets the value of has_registered when has_registered value is sent over by url_for(), False is default value if nothing gets sent
    illegal_comment = request.args.get("illegal_comment", False)
    login_form = LoginForm()
    if login_form.validate_on_submit():
        user = db.session.execute(db.select(User).where(User.email == login_form.email.data)).scalar()
        if user and check_password_hash(user.password, login_form.password.data):
            login_user(user)
            return redirect(url_for("get_all_posts"))
        elif user:
            return redirect(url_for("login", is_password_invalid=True))
        else:
            return redirect(url_for("login", is_email_invalid=True))
    is_password_invalid = request.args.get("is_password_invalid", None)
    is_email_invalid = request.args.get("is_email_invalid", None)
    return render_template("login.html", form=login_form, has_registered=has_registered,
                           is_password_invalid=is_password_invalid, is_email_invalid=is_email_invalid,
                           logged_in=current_user.is_authenticated, illegal_comment=illegal_comment)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('get_all_posts'))


@app.route('/')
def get_all_posts():
    print(current_user.is_authenticated)
    result = db.session.execute(db.select(BlogPost))
    posts = result.scalars().all()
    if current_user.is_authenticated:
        user_id = current_user.id
    else:
        user_id = None
    return render_template("index.html", all_posts=posts, logged_in=current_user.is_authenticated,
                           user_id=user_id)


# TODO: Allow logged-in users to comment on posts
@app.route("/post/<int:post_id>", methods=["POST", "GET"])
def show_post(post_id):
    requested_post = db.get_or_404(BlogPost, post_id)

    comment_form = CommentForm()
    if comment_form.validate_on_submit():
        if current_user.is_authenticated:
            new_comment = Comment(
                author_id=current_user.id,
                text=comment_form.body.data,
                post_id=post_id
            )
            db.session.add(new_comment)
            db.session.commit()
        else:
            return redirect(url_for("login", illegal_comment=True))

    all_comments = db.session.execute(db.select(Comment).where(Comment.post_id == post_id)).scalars().all()

    if current_user.is_authenticated:
        user_id = current_user.id
    else:
        user_id = None

    return render_template("post.html", post=requested_post, logged_in=current_user.is_authenticated,
                           user_id=user_id, form=comment_form, comments=all_comments)


# TODO: Use a decorator so only an admin user can create a new post
@app.route("/new-post", methods=["GET", "POST"])
@admin_only
def add_new_post():
    form = CreatePostForm()
    if form.validate_on_submit():
        new_post = BlogPost(
            author_id=current_user.id,
            title=form.title.data,
            subtitle=form.subtitle.data,
            body=form.body.data,
            img_url=form.img_url.data,
            date=date.today().strftime("%B %d, %Y")
        )
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for("get_all_posts"))
    return render_template("make-post.html", form=form, logged_in=current_user.is_authenticated)


# TODO: Use a decorator so only an admin user can edit a post
@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
@admin_only
def edit_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    edit_form = CreatePostForm(
        title=post.title,
        subtitle=post.subtitle,
        img_url=post.img_url,
        author=post.author,
        body=post.body
    )
    if edit_form.validate_on_submit():
        post.title = edit_form.title.data
        post.subtitle = edit_form.subtitle.data
        post.img_url = edit_form.img_url.data
        post.author = current_user
        post.body = edit_form.body.data
        db.session.commit()
        return redirect(url_for("show_post", post_id=post.id))
    return render_template("make-post.html", form=edit_form, is_edit=True, logged_in=current_user.is_authenticated)


# TODO: Use a decorator so only an admin user can delete a post
@app.route("/delete/<int:post_id>")
@admin_only
def delete_post(post_id):
    post_to_delete = db.get_or_404(BlogPost, post_id)
    db.session.delete(post_to_delete)
    db.session.commit()
    return redirect(url_for('get_all_posts'))


@app.route("/about")
def about():
    return render_template("about.html", logged_in=current_user.is_authenticated)


@app.route("/contact")
def contact():
    return render_template("contact.html", logged_in=current_user.is_authenticated)


if __name__ == "__main__":
    app.run(debug=False, port=5002)
