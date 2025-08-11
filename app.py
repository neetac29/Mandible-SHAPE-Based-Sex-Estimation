import streamlit as st
import pandas as pd
import os
from rapidfuzz import process

# Get the current file directory
BASE_DIR = os.path.dirname(__file__)
file_path = os.path.join(BASE_DIR, "skull_shapes.xlsx")

# Load Excel data
df = pd.read_excel("skull_shapes.xlsx", header=1)
df.columns = df.columns.str.strip()  # Remove extra spaces from column names
df['filename'] = df['filename'].str.lower()

# List of columns to display if they exist
desired_columns = [
    'ARCHITECTURE OF THE SKULL', 
    'SUPRAORBITAL MARGIN', 
    'MASTOID', 
    'OCCIPITAL PROTUBERANCE', 
    'FRONTAL EMINENCES', 
    'ORBITS', 
    'AP', 
    'TD', 
    'AP/TD', 
    'filename', 
    'SHAPE'
]

# Sex determination based on SHAPE
def get_sex_from_SHAPE(SHAPE):
    if pd.isna(SHAPE):
        return "Unknown"
    shape_lower = SHAPE.strip().lower()
    if shape_lower == "round":
        return "Female"
    elif shape_lower == "oval":
        return "Male"
    else:
        return "Unknown"

st.title("Mandible SHAPE-Based Sex Estimation")

# Upload image
uploaded_file = st.file_uploader("Upload Mandible Image", type=["jpg", "jpeg", "png"])
if uploaded_file:
    st.image(uploaded_file, caption="Uploaded Mandible", use_container_width=True)

    # Extract filename without extension
    uploaded_name = os.path.splitext(uploaded_file.name)[0].lower()

    # Try exact match first
    row = df[df['filename'] == uploaded_name]

    if row.empty:
        # If not found, use fuzzy matching
        choices = df['filename'].tolist()
        match, score, idx = process.extractOne(uploaded_name, choices)
        if score >= 80:  # match confidence threshold
            row = df.iloc[[idx]]

    if not row.empty:
        # Predict sex first
        SHAPE = row.iloc[0]['SHAPE'] if 'SHAPE' in row.columns else None
        sex = get_sex_from_SHAPE(SHAPE)
        st.success(f"Predicted SHAPE: {SHAPE if pd.notna(SHAPE) else 'N/A'} → Sex: {sex}")

        # Filter only existing & non-empty columns, exclude 'SL NO'
        available_cols = [
            col for col in desired_columns 
            if col in row.columns and col != 'SL NO' and not row[col].isna().all()
        ]
        row_filtered = row[available_cols]

        # Show details from Excel
        st.subheader("Details of Mandible Image from Excel")
        st.table(row_filtered)

    else:
        st.error("No matching record found in Excel.")
