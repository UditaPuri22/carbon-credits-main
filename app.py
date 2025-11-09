from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Activity, EmissionRecord,MarketplaceListing,Transaction,OffsetProgram,OffsetTransaction
from datetime import datetime

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


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/login", methods=["POST"])
def login():
    username = request.form["username"]
    password = request.form["password"]

    user = User.query.filter_by(username=username).first()

    if not user:
        # User doesn't exist
        return render_template("home.html", message="User does not exist", open_login=True)
    elif not check_password_hash(user.password, password):
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

# Dashboard route
@app.route('/dashboard')
@login_required
def dashboard():
    user = current_user

    
    emission_records = (
        db.session.query(Activity.date, func.sum(Activity.amount))
        .filter(Activity.user_id == user.id)
        .group_by(Activity.date)
        .order_by(Activity.date.asc())
        .all()
    )
    emission_data = [
        {"date": e[0].strftime("%Y-%m-%d"), "amount": round(e[1], 2)}
        for e in emission_records
    ]

   
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

    
    return render_template(
        'dashboard.html',
        user=user,
        emission_data=emission_data,
        marketplace_transactions=marketplace_data,
        offset_transactions=offset_transactions
    )



from models import Activity, EmissionFactor, EmissionRecord
from flask import render_template, request
from datetime import datetime

@app.route('/activity_entry', methods=['GET', 'POST'])
@login_required
def activity_entry():

    message = None


    if request.method == 'POST':
        activity_type = request.form.get('activity_type')
        description = request.form.get('description')
        amount = float(request.form.get('amount'))
        unit = request.form.get('unit')
        date_str = request.form.get('date')
        date = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else datetime.utcnow().date()

        
        factor = EmissionFactor.query.filter_by(activity_type=activity_type).first()
        if not factor:
            message = f"No emission factor found for {activity_type}."
        else:
            emission = amount * factor.factor  # kg CO₂ emitted

           
            activity = Activity(
                user_id=current_user.id,
                activity_type=activity_type,
                description=description,
                amount=amount,
                unit=unit,
                date=date
            )
            db.session.add(activity)

            
            emission_record = EmissionRecord(
                user_id=current_user.id,
                date=date,
                emission_value=emission
            )
            db.session.add(emission_record)
            db.session.commit()

            message = f"Activity for {date.strftime('%Y-%m-%d')} added successfully."


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
            # Deduct credits from user
            user.credits -= credits_required

            new_offset = OffsetTransaction(
                user_id=user.id,
                program_id=program.id,
                co2_offset=co2_amount,
                credits_used=credits_required,
                created_at=datetime.utcnow()
            )
            db.session.add(new_offset)
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




if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        if OffsetProgram.query.count() == 0:
            programs = [
                OffsetProgram(
                    name="Tree Plantation Drive",
                    description="Funds planting of new trees.",
                    rate_per_kg=0.5,
                    image="trees.jpg"
                ),
                OffsetProgram(
                    name="Renewable Energy Project",
                    description="Invests in solar/wind energy.",
                    rate_per_kg=0.8,
                    image="renewable.jpg"
                ),
                OffsetProgram(
                    name="Ocean Cleanup Program",
                    description="Supports ocean plastic cleanup.",
                    rate_per_kg=1.0,
                    image="ocean.jpg"
                )
            ]
            db.session.add_all(programs)
            db.session.commit()
            print(" Default offset programs added.")
    app.run(debug=True)
    

