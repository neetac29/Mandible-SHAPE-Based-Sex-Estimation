import streamlit as st
import pandas as pd
from PIL import Image
import imagehash
import gspread
from google.oauth2.service_account import Credentials
import os
import numpy as np
import re

# ===== GOOGLE SHEETS CONFIG =====
GOOGLE_SHEET_NAME = "skull_shapes"  # Replace with your sheet name

# Scopes for Google Sheets API
SCOPE = ["https://spreadsheets.google.com/feeds",
         "https://www.googleapis.com/auth/spreadsheets",
         "https://www.googleapis.com/auth/drive.file",
         "https://www.googleapis.com/auth/drive"
         ]
#  ===============for local run only ======================================================
# CREDS = Credentials.from_service_account_file("google_credentials.json", scopes=SCOPE)
# gc = gspread.authorize(CREDS)
# sheet = gc.open(GOOGLE_SHEET_NAME).sheet1
#  ===============for local run only ======================================================


# ========for streamlit cloude only========================================
# Load credentials from Streamlit secrets
creds_dict = st.secrets["google_credentials"]
creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPE)

# Authorize the client
client = gspread.authorize(creds)
sheet = client.open(GOOGLE_SHEET_NAME).sheet1

# ===========for streamlit cloude only=====================================


# ===== FUNCTIONS =====
def get_df():
    data = sheet.get_all_records()
    df = pd.DataFrame(data)

    # Clean and normalize column names
    cleaned_cols = [
        re.sub(r"\s+", " ", str(col)).strip().lower()
        for col in df.columns
    ]

    # Apply cleaned column names
    df.columns = cleaned_cols

    # Aliases to unify naming
    rename_map = {
        "file name": "filename",
        "sl no.": "sl no",
        "slno": "sl no"
    }
    df.rename(columns=rename_map, inplace=True)

    return df

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

def update_row_in_sheet(row_index, updated_values):
    sheet.update(f"A{row_index + 2}", [updated_values])  # row_index + 2 for header offset


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
    
def check_and_divide(ap, td):
    if ap and td:  # both present and not empty
        try:
            result = float(ap) / float(td)
            return result
        except ZeroDivisionError:
            return "Error: td cannot be zero."
        except ValueError:
            return "Error: ap and td must be numbers."
    elif ap and not td:
        return "Error: td is empty."
    elif td and not ap:
        return "Error: ap is empty."
    else:
        return ""


# ===== STREAMLIT UI =====
st.title("Foramen Magnum Metrics for Forensic Sex Estimation: Advancing Accuracy with Machine Learning")

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
    
    if "filename" not in df.columns or "image hash key" not in df.columns:
        st.error(f"Required columns not found. Available: {list(df.columns)}")
        st.stop()

    df["filename"] = df["filename"].astype(str).str.strip()
    df["image hash key"] = df["image hash key"].astype(str).str.strip()

    match_row = None
    match_index = None

    # Step 1: Match by filename
    filename_matches = df[df["filename"].str.lower() == filename_no_ext.lower()]
    if not filename_matches.empty:
        match_row = filename_matches.iloc[0]
        match_index = filename_matches.index[0]
        # Save hash if empty
        if not match_row["image hash key"]:
            save_hash_to_sheet(match_index, hash_key)
            st.info("Hash key saved for this image.")
        sex = get_sex_from_shape(match_row["shape"])
        st.success(f"Prediction of Image: {sex}")

    # Step 2: Match by hash (for same image, different filename)
    if match_row is None:
        hash_matches = df[df["image hash key"] == hash_key]
        if not hash_matches.empty:
            match_row = hash_matches.iloc[0]
            match_index = hash_matches.index[0]
            st.info("Same image detected (different filename).")
            sex = get_sex_from_shape(match_row["shape"])
            st.success(f"Prediction of Image: {sex}")

    # Step 3: No match found → prompt for new entry
    if match_row is None:
        st.warning("No match found. Please add details to Google Sheet.")

        # Auto increment sl no
        new_sl_no = df["sl no"].max() + 1 if not df.empty else 1

        with st.form("new_entry_form"):
            filename_input = st.text_input("filename", filename_no_ext)
            shape_input = st.selectbox("shape", ["ROUND", "OVAL"])

            ap_input = st.text_input("ap")  # get ap value from user
            td_input = st.text_input("td")  # get td value from user
            
            other_columns = [col for col in df.columns if col not in ["sl no", "filename", "shape", "image hash key", "ap", "td", "ap/td"]]
            extra_data = []
            for col in other_columns:
                extra_data.append(st.text_input(col))
            submitted = st.form_submit_button("Add to Sheet")

        if submitted:
            # Get the exact column order from the current DataFrame
            columns = df.columns.tolist()

            ratio = check_and_divide(ap_input, td_input)

            # Build row as a dictionary
            if isinstance(ratio, str) and ratio.startswith("Error"):
                st.error(ratio)
            else:
                new_data_dict = {
                    "sl no": new_sl_no,
                    "filename": filename_input,
                    "shape": shape_input,
                    "image hash key": hash_key,
                    "ap": ap_input,
                    "td": td_input,
                    "ap/td": ratio
                    
                }

                # Fill in any other columns from extra_data in correct order
                for col, val in zip(
                    [c for c in columns if c not in ["sl no", "filename", "shape", "image hash key", "ap", "td", "ap/td"]],
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
                st.rerun()

   # Step 4: Edit existing record with icon
    if match_row is not None and match_index is not None:
        if "edit_mode" not in st.session_state:
            st.session_state.edit_mode = False
        
        st.write("### Matched Record")
        col1, col2 = st.columns([8, 1])
        with col1:
            match_row_display = match_row.to_frame().T
            match_row_display.columns = [col.upper() for col in match_row_display.columns]
            st.dataframe(match_row_display)
        with col2:
            if st.button("✏️", key="edit_button"):
                st.session_state.edit_mode = True

        # Show edit form only when edit_mode is active
        if st.session_state.edit_mode:
            st.subheader("Edit Data")
            with st.form("edit_entry_form"):
                updated_values = []
                for col in df.columns:
                    updated_values.append(st.text_input(col, value=str(match_row[col])))
                save_changes = st.form_submit_button("Save Changes")

            if save_changes:
                update_row_in_sheet(match_index, updated_values)
                st.success("Row updated successfully!")
                st.session_state.edit_mode = False  # Close form
                st.rerun()
