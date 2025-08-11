import streamlit as st
import pandas as pd
from PIL import Image
import imagehash
import gspread
from google.oauth2.service_account import Credentials
import os
import numpy as np

# ===== GOOGLE SHEETS CONFIG =====
GOOGLE_SHEET_NAME = "skull_shapes"  # Replace with your sheet name
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
CREDS = Credentials.from_service_account_file("google_credentials.json", scopes=SCOPE)
gc = gspread.authorize(CREDS)
sheet = gc.open(GOOGLE_SHEET_NAME).sheet1

# ===== FUNCTIONS =====
def get_df():
    data = sheet.get_all_records()
    return pd.DataFrame(data)

def save_hash_to_sheet(row_index, hash_key):
    # +2 for header row and 0-index adjustment
    sheet.update_cell(row_index + 2, df.columns.get_loc("image hash key") + 1, str(hash_key))

def append_new_row(new_data):
    # Convert all NumPy/Pandas types to native Python types
    clean_data = []
    for v in new_data:
        if isinstance(v, (np.integer, int)):
            clean_data.append(int(v))
        elif isinstance(v, (np.floating, float)):
            clean_data.append(float(v))
        else:
            clean_data.append(str(v))
    sheet.append_row(clean_data)

def get_phash(image):
    return str(imagehash.phash(image))

def get_sex_from_shape(shape):
    shape = shape.strip().upper()
    if shape == "ROUND":
        return "Female"
    elif shape == "OVAL":
        return "Male"
    else:
        return "Unknown"

# ===== STREAMLIT UI =====
st.title("Mandible shape & Sex Detection")

uploaded_file = st.file_uploader("Upload an image", type=["jpg", "jpeg", "png"])

if uploaded_file:
    image = Image.open(uploaded_file).convert("RGB")
    st.image(image, caption="Uploaded Image", use_container_width=True)

    filename_no_ext = os.path.splitext(uploaded_file.name)[0].strip()
    hash_key = get_phash(image)

    df = get_df()
    df.columns = (
        df.columns.str.strip()
              .str.lower()
              .str.replace(r"\s+", " ", regex=True)
    )
    print("column::::::", df.columns)
    if "filename" not in df.columns or "image hash key" not in df.columns:
        st.error(f"Required columns not found. Available: {list(df.columns)}")
        st.stop()

    df["filename"] = df["filename"].astype(str).str.strip()
    df["image hash key"] = df["image hash key"].astype(str).str.strip()

    match_row = None

    # Step 1: Match by filename
    filename_matches = df[df["filename"].str.lower() == filename_no_ext.lower()]
    if not filename_matches.empty:
        match_row = filename_matches.iloc[0]
        # Save hash if empty
        if not match_row["image hash key"]:
            save_hash_to_sheet(filename_matches.index[0], hash_key)
            st.info("Hash key saved for this image.")
        sex = get_sex_from_shape(match_row["shape"])
        st.success(f"Prediction: {sex}")
        st.dataframe(match_row.to_frame().T)

    # Step 2: Match by hash (for same image, different filename)
    if match_row is None:
        hash_matches = df[df["image hash key"] == hash_key]
        if not hash_matches.empty:
            match_row = hash_matches.iloc[0]
            st.info("Same image detected (different filename).")
            sex = get_sex_from_shape(match_row["shape"])
            st.success(f"Prediction: {sex}")
            st.dataframe(match_row.to_frame().T)

    # Step 3: No match found → prompt for new entry
    if match_row is None:
        st.warning("No match found. Please add details to Google Sheet.")

        # Auto increment sl no
        new_sl_no = df["sl no"].max() + 1 if not df.empty else 1

        with st.form("new_entry_form"):
            filename_input = st.text_input("filename", filename_no_ext)
            shape_input = st.selectbox("shape", ["ROUND", "OVAL"])
            other_columns = [col for col in df.columns if col not in ["sl no", "filename", "shape", "image hash key"]]
            extra_data = []
            for col in other_columns:
                extra_data.append(st.text_input(col))
            submitted = st.form_submit_button("Add to Sheet")

        if submitted:
            # Get the exact column order from the current DataFrame
            columns = df.columns.tolist()

            # Build row as a dictionary
            new_data_dict = {
                "sl no": new_sl_no,
                "filename": filename_input,
                "shape": shape_input,
                "image hash key": hash_key
            }

            # Fill in any other columns from extra_data in correct order
            for col, val in zip(
                [c for c in columns if c not in ["sl no", "filename", "shape", "image hash key"]],
                extra_data
            ):
                new_data_dict[col] = val

            # Create ordered list for append_row based on sheet's column order
            new_row_ordered = [new_data_dict.get(col, "") for col in columns]

            clean_row = []
            for v in new_row_ordered:
                if hasattr(v, "item"):  # NumPy scalar
                    clean_row.append(v.item())
                else:
                    clean_row.append(v)

            # Append the row to Google Sheet
            append_new_row(clean_row)
            st.success("New entry added to Google Sheet.")
