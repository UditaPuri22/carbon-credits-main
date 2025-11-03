from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Activity, EmissionRecord,MarketplaceListing,Transaction
from datetime import datetime

app = Flask(__name__)
app.secret_key = "your_secret_key_here"

# Database setup
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///carbon_credits.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

# Login manager setup
login_manager = LoginManager(app)
login_manager.login_view = "home"

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Routes ---
@app.route("/")
def home():
    return render_template("home.html")

# Login route (from modal)
@app.route("/login", methods=["POST"])
def login():
    username = request.form["username"]
    password = request.form["password"]

    user = User.query.filter_by(username=username).first()
    if user and check_password_hash(user.password, password):
        login_user(user)
        flash(f"Welcome back, {username}!", "success")
        return redirect(url_for("dashboard"))
    else:
        flash("Invalid username or password", "danger")
        return redirect(url_for("home"))

@app.route("/register", methods=["POST"])
def register():
    username = request.form["username"]
    password = request.form["password"]

    # Check if user exists
    existing_user = User.query.filter_by(username=username).first()
    if existing_user:
        flash("Username already exists. Please choose another.", "warning")
        return redirect(url_for("home"))

    # Create new user
    hashed_pw = generate_password_hash(password)
    new_user = User(username=username, password=hashed_pw)
    db.session.add(new_user)
    db.session.commit()

    login_user(new_user)
    flash(f"Welcome, {username}! Your account has been created successfully.", "success")

    return redirect(url_for("dashboard"))

# Dashboard route
@app.route("/dashboard")
@login_required
def dashboard():
    activities = Activity.query.filter_by(user_id=current_user.id).all()
    return render_template(
        "dashboard.html",
        username=current_user.username,
        credits=current_user.credits,
        activities=activities
    )


@app.route("/activity", methods=["GET", "POST"])
@login_required
def activity_entry():
    message = request.args.get("message")  

    if request.method == "POST":
        activity_type = request.form["activity_type"]
        description = request.form["description"]
        amount = request.form["amount"]
        unit = request.form["unit"]
        date_str = request.form.get('date')
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()

        new_activity = Activity(
            user_id=current_user.id,
            activity_type=activity_type,
            description=description,
            amount=amount,
            unit=unit,
            date=date_obj
        )
        db.session.add(new_activity)
        db.session.commit()

       
        msg = f"Activity added successfully for {date_str}!"
      
        return redirect(url_for('activity_entry', message=msg))
    
   
    return render_template('activity_entry.html', message=message)

@app.route("/emission", methods=["GET", "POST"])
@login_required
def emission_calculation():
    daily_emission = None
    message = None

    if request.method == "POST":
        date_str = request.form.get("date")
        if not date_str:
            message = "Please select a date."
        else:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()

            
            existing_record = EmissionRecord.query.filter_by(
                user_id=current_user.id, date=date_obj
            ).first()

            if existing_record:
                daily_emission = existing_record.emission_value
                message = (
                    f"Emission for {date_str} was already calculated: "
                    f"{daily_emission:.2f} kg CO₂. "
                    f"Remaining credits: {current_user.credits:.2f}"
                )
            else:
               
                activities = Activity.query.filter_by(
                    user_id=current_user.id, date=date_obj
                ).all()

                if not activities:
                    message = f"No activities found for {date_str}."
                else:
                    emission_factors = {
                        "Car Travel": 0.12,
                        "Flight": 0.25,
                        "Electricity Usage": 0.85,
                        "Bus Travel": 0.06,
                        "Bike Travel": 0.02
                    }

                    daily_emission = 0
                    for act in activities:
                        factor = emission_factors.get(act.activity_type, 0.1)
                        daily_emission += float(act.amount) * factor

                   
                    current_user.credits -= daily_emission
                    if current_user.credits < 0:
                        current_user.credits = 0

                   
                    new_record = EmissionRecord(
                        user_id=current_user.id,
                        date=date_obj,
                        emission_value=daily_emission
                    )
                    db.session.add(new_record)
                    db.session.commit()

                    message = (
                        f"Emission for {date_str} calculated successfully: "
                        f"{daily_emission:.2f} kg CO₂. "
                        f"Remaining credits: {current_user.credits:.2f}"
                    )

    return render_template("emission_calculation.html", message=message, daily_emission=daily_emission)

# ---------------- MARKETPLACE ----------------

@app.route("/marketplace")
@login_required
def marketplace():
   
    listings = MarketplaceListing.query.filter(
        MarketplaceListing.status == "available",
        MarketplaceListing.user_id != current_user.id
    ).all()

   
    user_listings = MarketplaceListing.query.filter_by(user_id=current_user.id).all()

    return render_template("marketplace.html", listings=listings, user_listings=user_listings)


@app.route("/create_listing", methods=["GET", "POST"])
@login_required
def create_listing():
    msg = None
    success = False

    if request.method == "POST":
        credits = float(request.form["credits"])
        price_per_credit = float(request.form["price_per_credit"])

        if current_user.credits < credits:
            msg = "You don’t have enough credits to list this amount."
        else:
            total_price = credits * price_per_credit
            listing = MarketplaceListing(
                user_id=current_user.id,
                credits=credits,
                price_per_credit=price_per_credit,
                total_price=total_price,
            )
            current_user.credits -= credits
            db.session.add(listing)
            db.session.commit()

            flash("Listing created successfully!", "success")
           
            return redirect(url_for("marketplace"))

    return render_template("create_listing.html", message=msg, success=success)


@app.route("/buy/<int:listing_id>", methods=["POST"])
@login_required
def buy_credits(listing_id):
    listing = MarketplaceListing.query.get_or_404(listing_id)

   
    if listing.user_id == current_user.id:
        flash("You cannot buy your own listing!", "warning")
        return redirect(url_for("marketplace"))

  
    if listing.status == "sold":
        flash("This listing is already sold!", "danger")
        return redirect(url_for("marketplace"))

    seller = User.query.get(listing.user_id)

   
    if current_user.wallet_balance < listing.total_price:
        flash("You don’t have enough balance in your wallet!", "danger")
        return redirect(url_for("marketplace"))

    # --- Perform transaction ---
    
    current_user.wallet_balance -= listing.total_price
    current_user.credits += listing.credits

   
    seller.wallet_balance += listing.total_price

   
    listing.status = "sold"

   
    transaction = Transaction(
        buyer_id=current_user.id,
        seller_id=seller.id,
        credits_transferred=listing.credits,
        total_amount=listing.total_price,
    )

    db.session.add(transaction)
    db.session.commit()

    return render_template(
        "purchase_success.html",
        listing=listing,
        buyer=current_user,
        seller=seller
    )


# Logout
@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You’ve been logged out successfully.", "info")
    return redirect(url_for("home"))

# Initialize DB
with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True)
