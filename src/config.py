import os

# Define the root of the project
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Define a cross-platform output directory
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

# Ensure it exists
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
