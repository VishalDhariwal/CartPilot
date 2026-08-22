import json
import random

merchants = [
    "TechHaven", "GamerGear", "OfficeSuppliesCo", "HomeEssentials", "FashionHub",
    "SneakerWorld", "KitchenKing", "BookWorm", "PetPalace", "OutdoorAdventures",
    "BeautyBliss", "AutoPartsPro", "ToyUniverse", "MusicMakers", "FitnessFreaks",
    "ArtisanCrafts", "GourmetGrocer", "HardwareHeroes", "GardenOasis", "JewelryBox"
]

categories = ["electronics", "kitchenware", "grocery", "fashion", "home"]

item_names = {
    "electronics": ["Laptop", "Smartphone", "Tablet", "Monitor", "Keyboard", "Mouse", "Headphones", "Earbuds", "Smartwatch", "Charger"],
    "kitchenware": ["Pan", "Pot", "Knife", "Spatula", "Blender", "Mixer", "Oven", "Microwave", "Toaster", "Kettle"],
    "grocery": ["Rice", "Wheat", "Milk", "Eggs", "Bread", "Butter", "Cheese", "Apples", "Bananas", "Tomatoes"],
    "fashion": ["T-Shirt", "Jeans", "Jacket", "Shoes", "Socks", "Hat", "Scarf", "Gloves", "Belt", "Sunglasses"],
    "home": ["Bed", "Sofa", "Chair", "Table", "Lamp", "Rug", "Curtains", "Cushion", "Mirror", "Clock"]
}

catalog = []
sku_counter = 1

for merchant in merchants:
    # Each merchant gets a dominant category
    dominant_category = random.choice(categories)
    
    for i in range(50):
        category = dominant_category if random.random() > 0.3 else random.choice(categories)
        base_name = random.choice(item_names[category])
        
        # Generate a unique variant name
        adjectives = ["Pro", "Max", "Ultra", "Lite", "Plus", "Essential", "Premium", "Classic", "Modern", "Vintage"]
        variant_name = f"{base_name} {random.choice(adjectives)} {random.randint(100, 999)}"
        
        sku = f"{merchant[:3].upper()}-{category[:3].upper()}-{sku_counter:04d}"
        
        # Prices in paise (e.g. 50000 = 500 Rs)
        price_paise = random.randint(10000, 200000) # 100 Rs to 2000 Rs
        
        # Laptops should be more expensive
        if base_name == "Laptop":
            price_paise = random.randint(3000000, 9000000) # 30k to 90k Rs
            
        catalog.append({
            "sku": sku,
            "name": variant_name,
            "price_paise": price_paise,
            "stock": random.randint(0, 100),
            "category": category,
            "merchant": merchant
        })
        sku_counter += 1

with open("seed_catalog.json", "w") as f:
    json.dump(catalog, f, indent=2)

print(f"Generated {len(catalog)} items.")
