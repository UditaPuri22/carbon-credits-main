from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

from models import (
    db, User, Activity, EmissionFactor, EmissionRecord,
    MarketplaceListing, Transaction, OffsetProgram, OffsetTransaction
)


# Flask App Configuration
app = Flask(__name__)
app.secret_key = "your_secret_key_here"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///carbon_credits.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = "home"

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Homepage & Authentication
@app.route("/")
def home():
    return render_template("home.html")

@app.route("/login", methods=["POST"])
def login():
    username = request.form["username"]
    password = request.form["password"]
    user = User.query.filter_by(username=username).first()

    if not user:
        return render_template("home.html", message="User does not exist", open_login=True)
    if not check_password_hash(user.password, password):
        return render_template("home.html", message="Invalid username or password", open_login=True)

    login_user(user)
    return redirect(url_for("dashboard"))

@app.route("/register", methods=["POST"])
def register():
    username = request.form["username"]
    password = request.form["password"]

    existing_user = User.query.filter_by(username=username).first()
    if existing_user:
        return render_template("home.html", message="Username already exists. Please login.", open_signup=True)

    hashed_pw = generate_password_hash(password)
    new_user = User(username=username, password=hashed_pw)
    db.session.add(new_user)
    db.session.commit()

    login_user(new_user)
    return redirect(url_for("dashboard"))

# Emission Factors (kg CO₂e/unit)
EMISSION_FACTORS = {
    # --- Home Energy ---
    "Electricity Usage": 0.82, "Natural Gas Usage": 1.90, "LPG Usage": 1.55,
    "Biogas Usage": 0.10, "Heating Oil": 2.70, "Coal Usage": 2.40,
    "Renewable Energy Purchase": -0.82,

    # --- Transport ---
    "Car (Petrol) Travel": 0.21, "Car (Diesel) Travel": 0.25,
    "Motorcycle Travel": 0.07, "Bus Travel": 0.09,
    "Train Travel": 0.04, "Metro Travel": 0.05,
    "Flight - Domestic": 0.18, "Flight - International": 0.14,
    "Electric Vehicle Travel": 0.10, "Bicycle Travel": 0.00,

    # --- Food & Diet ---
    "Mutton Consumption": 24.0, "Chicken Consumption": 6.9,
    "Fish Consumption": 5.5, "Dairy Consumption": 1.2,
    "Vegetarian Diet": 3.5, "Vegan Diet": 2.5,

    # --- Goods & Services ---
    "Clothing Purchase": 0.005, "Electronics Purchase": 0.008,
    "Furniture Purchase": 0.006, "Waste Generated": 1.0,

    # --- Offsets ---
    "Tree Planting": -20, "Carbon Credit Purchase": -1000,
    "Renewable Energy Support": -500, "Biogas Program Support": -300
}

# Dashboard with Emission, Marketplace, Offset & Activity History
@app.route('/dashboard')
@login_required
def dashboard():
    user = current_user

    # --- Emission records (by date) ---
    emission_records = (
        db.session.query(EmissionRecord.date, func.sum(EmissionRecord.emission_value))
        .filter(EmissionRecord.user_id == user.id)
        .group_by(EmissionRecord.date)
        .order_by(EmissionRecord.date.asc())
        .all()
    )
    emission_data = [
        {"date": e[0].strftime("%Y-%m-%d"), "amount": round(e[1], 2)} for e in emission_records
    ]

    # --- Marketplace transactions ---
    marketplace_transactions = (
        db.session.query(Transaction, User.username)
        .join(User, Transaction.seller_id == User.id)
        .filter(Transaction.buyer_id == user.id)
        .order_by(Transaction.created_at.desc())
        .all()
    )
    marketplace_data = [
        {
            "date": t.Transaction.created_at.strftime("%Y-%m-%d"),
            "program_name": f"Bought from {t.username}",
            "credits_used": t.Transaction.credits_transferred,
        }
        for t in marketplace_transactions
    ]

    # --- Offset transactions ---
    offset_data = (
        db.session.query(OffsetTransaction, OffsetProgram)
        .join(OffsetProgram, OffsetTransaction.program_id == OffsetProgram.id)
        .filter(OffsetTransaction.user_id == user.id)
        .order_by(OffsetTransaction.created_at.desc())
        .all()
    )
    offset_transactions = [
        {
            "date": record.OffsetTransaction.created_at.strftime("%Y-%m-%d"),
            "program_name": record.OffsetProgram.name,
            "co2_offset": record.OffsetTransaction.co2_offset,
            "credits_spent": record.OffsetTransaction.credits_used,
        }
        for record in offset_data
    ]

    # --- Activity History (with date filter) ---
    filter_date = request.args.get('date')
    query = Activity.query.filter_by(user_id=user.id)
    if filter_date:
        try:
            date_obj = datetime.strptime(filter_date, "%Y-%m-%d").date()
            query = query.filter(Activity.date == date_obj)
        except ValueError:
            pass

    activities = query.order_by(Activity.date.desc()).all()

    # --- Emission factors ---
    db_factors = {ef.activity_type: ef.factor for ef in EmissionFactor.query.all()}
    emission_factors = db_factors if db_factors else EMISSION_FACTORS

    # --- Compute emissions & remaining credits ---
    activity_data = []
    remaining_credits = user.credits
    for act in activities:
        factor = emission_factors.get(act.activity_type, 0.1)
        emission = act.amount * factor  # kg CO₂e
        remaining_credits -= emission / 1000  # convert to tonnes
        activity_data.append({
            "date": act.date.strftime("%Y-%m-%d"),
            "type": act.activity_type,
            "unit": act.unit,
            "amount": act.amount,
            "emission": round(emission, 2),
            "remaining_credits": round(remaining_credits, 3)
        })

    return render_template(
        'dashboard.html',
        user=user,
        emission_data=emission_data,
        marketplace_transactions=marketplace_data,
        offset_transactions=offset_transactions,
        activity_data=activity_data,
        filter_date=filter_date
    )

# Activity Entry
@app.route('/activity_entry', methods=['GET', 'POST'])
@login_required
def activity_entry():
    message = None

    if request.method == 'POST':

        # Get lists for all fields
        activity_types = request.form.getlist('activity_type[]')
        descriptions = request.form.getlist('description[]')
        amounts = request.form.getlist('amount[]')
        units = request.form.getlist('unit[]')
        dates = request.form.getlist('date[]')

        total_emission = 0  # to show combined summary

        for i in range(len(activity_types)):
            if not activity_types[i].strip():
                continue  # skip empty rows

            activity_type = activity_types[i]
            description = descriptions[i]
            amount = float(amounts[i])
            unit = units[i]

            # Parse date
            date_str = dates[i]
            date = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else datetime.utcnow().date()

            # Get emission factor
            factor_record = EmissionFactor.query.filter_by(activity_type=activity_type).first()
            factor = factor_record.factor if factor_record else EMISSION_FACTORS.get(activity_type, 0.1)

            # Emission calculation
            emission_value = amount * factor  # kg CO2e
            total_emission += emission_value

            # Update user credits
            current_user.credits -= emission_value / 1000  # convert to tCO2e
            if current_user.credits < 0:
                current_user.credits = 0
            db.session.add(current_user)

            # Log activity
            db.session.add(Activity(
                user_id=current_user.id,
                activity_type=activity_type,
                description=description,
                amount=amount,
                unit=unit,
                date=date
            ))

            # Log emission
            db.session.add(EmissionRecord(
                user_id=current_user.id,
                date=date,
                emission_value=emission_value
            ))

        db.session.commit()

        '''message = (
            f"Successfully saved {len(activity_types)} activities. "
            f"Total emissions: {total_emission:.2f} kg CO₂e. "
            f"Remaining credits: {current_user.credits:.2f} tCO₂e."
        )'''

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
            return render_template("emission.html", message=message)

        # Convert input text → date
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()

        # Fetch all activites of that date
        activities = Activity.query.filter_by( user_id=current_user.id, date=date_obj).all()

        if not activities:
            message = f"No activities found for {date_str}."
            return render_template("emission.html", message=message)

        # Compute the total emissions
        total_emission = 0.0
        for a in activities:
            factor_record = EmissionFactor.query.filter_by( activity_type=a.activity_type).first()
            factor = factor_record.factor if factor_record else EMISSION_FACTORS.get(a.activity_type, 0)

            total_emission += a.amount * factor

        # Save emission record for the day
        record = EmissionRecord( user_id=current_user.id, date=date_obj, emission_value=total_emission)
        db.session.add(record)
        db.session.commit()

        message = ( f"Total emission for {date_str}: {total_emission:.3f} kg CO₂e.")
        daily_emission = total_emission

    return render_template("emission_calculation.html", message=message, daily_emission=daily_emission)


# Marketplace
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
    msg, success = None, False
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

    current_user.wallet_balance -= listing.total_price
    current_user.credits += listing.credits
    seller.wallet_balance += listing.total_price
    listing.status = "sold"

    db.session.add(Transaction(
        buyer_id=current_user.id,
        seller_id=seller.id,
        credits_transferred=listing.credits,
        total_amount=listing.total_price,
    ))
    db.session.commit()

    return render_template("purchase_success.html", listing=listing, buyer=current_user, seller=seller)

# Offset Programs
@app.route('/offset', methods=['GET', 'POST'])
@login_required
def offset():
    message = None
    user = User.query.get(current_user.id)
    programs = OffsetProgram.query.all()

    if request.method == 'POST':
        program_id = request.form.get('program_id')
        co2_amount = float(request.form.get('co2_amount'))
        program = OffsetProgram.query.get(program_id)

        credits_required = program.rate_per_kg * co2_amount
        if user.credits < credits_required:
            message = f"Not enough credits! You need {credits_required:.2f} but have {user.credits:.2f}."
        else:
            user.credits -= credits_required
            db.session.add(OffsetTransaction(
                user_id=user.id, program_id=program.id,
                co2_offset=co2_amount, credits_used=credits_required,
                created_at=datetime.utcnow()
            ))
            db.session.commit()
            message = (
                f"Successfully offset {co2_amount:.2f} kg CO₂ via {program.name}. "
                f"{credits_required:.2f} credits deducted. "
                f"Remaining balance: {user.credits:.2f} credits."
            )

    return render_template('offset.html', programs=programs, message=message, user=user)

# Logout
@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You’ve been logged out successfully.", "info")
    return redirect(url_for("home"))

# Initialization
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        if OffsetProgram.query.count() == 0:
            programs = [
                OffsetProgram(name="Tree Plantation Drive", description="Funds planting of new trees.", rate_per_kg=0.5, image="trees.jpg"),
                OffsetProgram(name="Renewable Energy Project", description="Invests in solar/wind energy.", rate_per_kg=0.8, image="renewable.jpg"),
                OffsetProgram(name="Ocean Cleanup Program", description="Supports ocean plastic cleanup.", rate_per_kg=1.0, image="ocean.jpg")
            ]
            db.session.add_all(programs)
            db.session.commit()
            print("Default offset programs added.")
    app.run(debug=True)
