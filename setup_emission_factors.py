from app import db  
from models import EmissionFactor

def initialize_emission_factors():
    factors = {
    # --- 🏠 Home Energy ---
    "Electricity Usage": 0.82,             # per kWh (India grid average)
    "Natural Gas Usage": 1.90,             # per m³ (PNG)
    "LPG Usage": 1.55,                     # per liter
    "Biogas Usage": 0.10,                  # per m³ (low-emission renewable)
    "Heating Oil": 2.70,                   # per liter (rare in India)
    "Coal Usage": 2.40,                    # per kg
    "Renewable Energy Purchase": -0.82,    # offset equivalent of grid emissions

    # --- 🚗 Transport ---
    "Car (Petrol) Travel": 0.21,           # per km
    "Car (Diesel) Travel": 0.25,           
    "Motorcycle Travel": 0.07,             
    "Bus Travel": 0.09,                    # per passenger-km
    "Train Travel": 0.04,                  # per passenger-km (electric)
    "Metro Travel": 0.05,                  
    "Flight - Domestic": 0.18,             # per passenger-km
    "Flight - International": 0.14,        
    "Electric Vehicle Travel": 0.10,       # per km 
    "Bicycle Travel": 0.00,                # per km (zero emissions)

    # --- 🍽️ Food & Diet ---
    "Mutton Consumption": 24.0,            # per kg 
    "Chicken Consumption": 6.9,            
    "Fish Consumption": 5.5,               
    "Dairy Consumption": 1.2,              # per liter milk
    "Vegetarian Diet": 3.5,                # per day (kg CO₂e/day)
    "Vegan Diet": 2.5,                     # per day

    # --- 🛍️ Goods & Services ---
    "Clothing Purchase": 0.005,            # per ₹1 spent
    "Electronics Purchase": 0.008,         
    "Furniture Purchase": 0.006,           
    "Waste Generated": 1.0,                # per kg

    # --- 🌱 Offsets & Credits ---
    "Tree Planting": -20,                  # absorbs ~20 kg CO₂ per tree
    "Carbon Credit Purchase": -1000,       # each credit offsets 1 tCO₂
    "Renewable Energy Support": -500,      # per project/household support
    "Biogas Program Support": -300         # household-scale offset estimate
}

    for activity_type, factor in factors.items():
        existing = EmissionFactor.query.filter_by(activity_type=activity_type).first()
        if not existing:
            db.session.add(EmissionFactor(activity_type=activity_type, factor=factor))
        else:
            existing.factor = factor  # update if it already exists

    db.session.commit()
    print("✅ Emission factors initialized/updated successfully.")
