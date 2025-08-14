
import io
from typing import Dict, List, Optional, Tuple

import streamlit as st
import pandas as pd
from PIL import Image
import imagehash
import gspread
from google.oauth2.service_account import Credentials

# ==============================
# CONFIG
# ==============================
SHEET_TITLE = "skull_shapes"
HEADERS: List[str] = [
    "SL NO",
    "ARCHITECTURE OF THE SKULL",
    "OCCIPITAL CONDYLES",
    "MASTOID PROCESS",
    "OCCIPITAL PROTUBERANCE",
    "PALATAL WIDTH",
    "AP",
    "TD",
    "AP/TD",
    "FILE NAME",
    "SHAPE",
    "IMAGE HASH KEY",
]
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive",
]

#  ===============for local run only ======================================================
SERVICE_ACCOUNT_FILE = "google_credentials.json"
#  ===============for local run only ======================================================




st.set_page_config(page_title="Skull Shapes – Forensic Sex Estimation", page_icon="🦴", layout="centered")

# ==============================
# SESSION STATE (persistent across reruns)
# ==============================
if "editing_row_number" not in st.session_state:
    st.session_state.editing_row_number = None  # int sheet row to edit
if "editing_defaults" not in st.session_state:
    st.session_state.editing_defaults = {}
if "postsave_pending" not in st.session_state:
    st.session_state.postsave_pending = False
if "postsave_mode" not in st.session_state:
    st.session_state.postsave_mode = None  # "created" | "updated"
if "postsave_row_number" not in st.session_state:
    st.session_state.postsave_row_number = None
if "postsave_sl_no" not in st.session_state:
    st.session_state.postsave_sl_no = None

# ==============================
# GOOGLE SHEETS HELPERS
# ==============================
@st.cache_resource(show_spinner=False)
def get_gs_client() -> gspread.Client:
    # for local run
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)

    # ========for streamlit cloude only========================================
    # Load credentials from Streamlit secrets
    # creds_dict = st.secrets["google_credentials"] 
    # creds = Credentials.from_service_account_file(creds_dict, scopes=SCOPES)
    # ===========for streamlit cloude only=====================================


    return gspread.authorize(creds)


def ensure_spreadsheet_and_headers(client: gspread.Client) -> Tuple[gspread.Spreadsheet, gspread.Worksheet]:
    try:
        sh = client.open(SHEET_TITLE)
    except gspread.SpreadsheetNotFound:
        sh = client.create(SHEET_TITLE)
    ws = sh.sheet1

    existing_headers = ws.row_values(1)
    if existing_headers != HEADERS:
        ws.resize(1)
        ws.update("A1", [HEADERS])
    return sh, ws


def read_df(ws: gspread.Worksheet) -> pd.DataFrame:
    values = ws.get_all_values()
    if not values:
        return pd.DataFrame(columns=HEADERS)
    header_row = values[0]
    data_rows = values[1:] if len(values) > 1 else []
    if header_row != HEADERS:
        ws.update("A1", [HEADERS])
        header_row = HEADERS
    df = pd.DataFrame(data_rows, columns=header_row)
    if not df.empty:
        df.insert(0, "_ROW_NUMBER", range(2, 2 + len(df)))
    return df

# ==============================
# IMAGE / HASH HELPERS
# ==============================

def compute_image_hash(file_bytes: bytes) -> str:
    with Image.open(io.BytesIO(file_bytes)) as img:
        ahash = imagehash.average_hash(img)
    return str(ahash)

# ==============================
# BUSINESS LOGIC
# ==============================

def next_sl_no(df: pd.DataFrame) -> int:
    if df.empty or "SL NO" not in df.columns:
        return 1
    nums = pd.to_numeric(df["SL NO"], errors="coerce").dropna()
    return int(nums.max()) + 1 if not nums.empty else 1


def find_by_filename(df: pd.DataFrame, filename: str) -> Optional[pd.Series]:
    if df.empty or "FILE NAME" not in df.columns:
        return None
    m = df["FILE NAME"].str.strip().str.lower() == filename.strip().lower()
    return df[m].iloc[0] if m.any() else None


def find_by_hash(df: pd.DataFrame, img_hash: str) -> Optional[pd.Series]:
    if df.empty or "IMAGE HASH KEY" not in df.columns:
        return None
    m = df["IMAGE HASH KEY"].astype(str).str.strip().str.lower() == img_hash.strip().lower()
    return df[m].iloc[0] if m.any() else None


def predict_sex_from_shape(shape_value: str) -> Optional[str]:
    if not shape_value:
        return None
    s = shape_value.strip().lower()
    if s == "round":
        return "Female"
    if s == "oval":
        return "Male"
    return None


def update_row(ws: gspread.Worksheet, row_number: int, row_dict: Dict[str, str]) -> None:
    ap = row_dict.get("AP", "").strip()
    td = row_dict.get("TD", "").strip()
    ratio = ""
    if ap and td:
        try:
            ap_f, td_f = float(ap), float(td)
            if td_f != 0:
                ratio = str(ap_f / td_f)
        except ValueError:
            ratio = ""
    row_dict["AP/TD"] = ratio

    values = [row_dict.get(col, "") for col in HEADERS]
    start_col = "A"
    end_col = chr(ord("A") + len(HEADERS) - 1)
    ws.update(f"{start_col}{row_number}:{end_col}{row_number}", [values])


def append_row(ws: gspread.Worksheet, row_dict: Dict[str, str]) -> None:
    ap = row_dict.get("AP", "")
    td = row_dict.get("TD", "")
    ratio = ""
    if ap and td:
        try:
            ap_f, td_f = float(ap), float(td)
            if td_f != 0:
                ratio = str(ap_f / td_f)
        except ValueError:
            ratio = ""
    row_dict["AP/TD"] = ratio

    values = [row_dict.get(col, "") for col in HEADERS]
    ws.append_row(values, value_input_option="USER_ENTERED")

# ==============================
# UI HELPERS
# ==============================

def show_record_table(record: pd.Series):
    df_display = pd.DataFrame([record[HEADERS].to_dict()])
    st.dataframe(df_display, use_container_width=True)


def render_create_or_edit_form(*, mode: str, ws: gspread.Worksheet, df: pd.DataFrame, defaults: Dict[str, str], row_number: Optional[int] = None):
    is_create = mode == "create"

    with st.form(key=f"form_{mode}_{row_number or 'new'}"):
        col1, col2 = st.columns(2)

        sl_no = next_sl_no(df) if is_create else defaults.get("SL NO", "")

        with col1:
            st.text_input("SL NO", value=str(sl_no), disabled=True)
            architecture = st.text_input("ARCHITECTURE OF THE SKULL", value=defaults.get("ARCHITECTURE OF THE SKULL", ""))
            occipital_condyles = st.text_input("OCCIPITAL CONDYLES", value=defaults.get("OCCIPITAL CONDYLES", ""))
            mastoid_process = st.text_input("MASTOID PROCESS", value=defaults.get("MASTOID PROCESS", ""))
            occipital_protuberance = st.text_input("OCCIPITAL PROTUBERANCE", value=defaults.get("OCCIPITAL PROTUBERANCE", ""))
            palatal_width = st.text_input("PALATAL WIDTH", value=defaults.get("PALATAL WIDTH", ""))
        with col2:
            ap = st.text_input("AP", value=defaults.get("AP", ""))
            td = st.text_input("TD", value=defaults.get("TD", ""))
            preview = ""
            if ap and td:
                try:
                    ap_v, td_v = float(ap), float(td)
                    if td_v != 0:
                        preview = f"{ap_v / td_v}"
                except ValueError:
                    preview = ""
            st.text_input("AP/TD", value=preview, disabled=True, help="Auto-calculated from AP and TD")

            file_name = st.text_input("FILE NAME", value=defaults.get("FILE NAME", ""), disabled=is_create)
            shape = st.selectbox("SHAPE", options=["", "Round", "Oval"], index=["", "Round", "Oval"].index(defaults.get("SHAPE", "") if defaults.get("SHAPE", "") in ["Round", "Oval"] else ""))
            image_hash_key = st.text_input("IMAGE HASH KEY", value=defaults.get("IMAGE HASH KEY", ""), disabled=True)

        submitted = st.form_submit_button("Save to Google Sheet")

    if not submitted:
        return

    # Validation
    if (ap and not td) or (td and not ap):
        st.error("If you enter AP, you must also enter TD — and vice versa. If both are empty, that's allowed.")
        return

    row_dict = {
        "SL NO": str(sl_no),
        "ARCHITECTURE OF THE SKULL": architecture,
        "OCCIPITAL CONDYLES": occipital_condyles,
        "MASTOID PROCESS": mastoid_process,
        "OCCIPITAL PROTUBERANCE": occipital_protuberance,
        "PALATAL WIDTH": palatal_width,
        "AP": ap,
        "TD": td,
        "AP/TD": "",
        "FILE NAME": file_name if file_name else defaults.get("FILE NAME", ""),
        "SHAPE": shape,
        "IMAGE HASH KEY": image_hash_key,
    }

    if is_create:
        append_row(ws, row_dict)
        # Mark post-save state for create
        st.session_state.postsave_pending = True
        st.session_state.postsave_mode = "created"
        st.session_state.postsave_sl_no = int(sl_no)
        st.session_state.postsave_row_number = None
        st.session_state.editing_row_number = None
        st.success("New record created in Google Sheet.")
        st.rerun()
    else:
        if row_number is None:
            st.error("Internal error: row number missing for edit.")
            return
        update_row(ws, row_number, row_dict)
        # Mark post-save state for edit
        st.session_state.postsave_pending = True
        st.session_state.postsave_mode = "updated"
        st.session_state.postsave_row_number = int(row_number)
        st.session_state.postsave_sl_no = None
        st.session_state.editing_row_number = None
        st.success("Record updated in Google Sheet.")
        st.rerun()


def show_postsave_block(ws: gspread.Worksheet) -> bool:
    """If there is a post-save event pending, display the prediction + table and return True.
    Otherwise return False."""
    if not st.session_state.postsave_pending:
        return False

    df_latest = read_df(ws)
    rec = None

    if st.session_state.postsave_mode == "updated" and st.session_state.postsave_row_number is not None:
        rn = st.session_state.postsave_row_number
        m = df_latest["_ROW_NUMBER"] == rn
        if m.any():
            rec = df_latest[m].iloc[0]
    elif st.session_state.postsave_mode == "created" and st.session_state.postsave_sl_no is not None:
        sl = st.session_state.postsave_sl_no
        try:
            m = df_latest["SL NO"].astype(int) == int(sl)
        except Exception:
            m = df_latest["SL NO"] == str(sl)
        if m.any():
            rec = df_latest[m].iloc[0]

    if rec is None:
        st.warning("Saved, but could not immediately fetch the record. Try refreshing.")
        # Clear state to avoid loop
        st.session_state.postsave_pending = False
        st.session_state.postsave_mode = None
        st.session_state.postsave_row_number = None
        st.session_state.postsave_sl_no = None
        return False

    # Show prediction + table
    prediction = predict_sex_from_shape(rec.get("SHAPE", ""))
    if prediction:
        st.success(f"Prediction of Image: **{prediction}** ")
    else:
        st.warning("No valid SHAPE set (use 'Round' or 'Oval') → cannot predict.")

    st.markdown("**Record**")
    show_record_table(rec)

    colA, colB = st.columns([1, 3])
    with colA:
        if st.button("OK"):
            st.session_state.postsave_pending = False
            st.session_state.postsave_mode = None
            st.session_state.postsave_row_number = None
            st.session_state.postsave_sl_no = None
            st.rerun()
    return True

# ==============================
# MAIN APP
# ==============================


def main():
    st.title("🦴 Foramen Magnum Metrics for Forensic Sex Estimation: Advancing Accuracy with Machine Learning")
    st.caption("Matches by file name or image hash, predicts sex from SHAPE, and syncs with Google Sheets.")

    # Google auth
    try:
        client = get_gs_client()
    except Exception as e:
        st.error("Google auth failed. Ensure service_account.json is in project root and APIs are enabled.")
        st.exception(e)
        return

    sh, ws = ensure_spreadsheet_and_headers(client)
    df = read_df(ws)

    # If we just saved something, show the post-save view and stop
    if show_postsave_block(ws):
        return

    # Upload widget (persist uploaded image in session state)
    uploaded = st.file_uploader("Upload an image", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=False)
    
    # Detect if file is removed
    if uploaded is None:
        # Clear session state
        st.session_state.pop("uploaded_bytes", None)
    
    if uploaded is not None:
        st.session_state["uploaded_file"] = uploaded
        st.session_state["uploaded_bytes"] = uploaded.read()
        st.session_state["uploaded_name"] = uploaded.name

    # Display persisted image if available
    if "uploaded_file" in st.session_state and "uploaded_bytes" in st.session_state:
        st.image(st.session_state["uploaded_bytes"], caption=st.session_state["uploaded_name"], use_container_width=True)
    else:
        st.info("Upload an image to match against Google Sheet and proceed.")
        return

    file_name = st.session_state["uploaded_name"]
    bytes_data = st.session_state["uploaded_bytes"]
    img_hash = compute_image_hash(bytes_data)

    # If sheet has no rows yet
    if df.empty:
        st.subheader("Create First Entry")
        defaults = {"FILE NAME": file_name, "IMAGE HASH KEY": img_hash}
        render_create_or_edit_form(mode="create", ws=ws, df=df, defaults=defaults)
        return

    # If editing in progress
    if st.session_state.editing_row_number is not None:
        st.info("Editing selected record…")
        render_create_or_edit_form(
            mode="edit",
            ws=ws,
            df=df,
            defaults=st.session_state.editing_defaults,
            row_number=st.session_state.editing_row_number,
        )
        if st.button("Cancel editing"):
            st.session_state.editing_row_number = None
            st.session_state.editing_defaults = {}
            st.rerun()
        return

    # Try by FILE NAME
    row_by_name = find_by_filename(df, file_name)
    if row_by_name is not None:
        # st.success("Found a match by FILE NAME.")
        row_number = int(row_by_name["_ROW_NUMBER"])

        # Ensure hash is saved
        if not str(row_by_name.get("IMAGE HASH KEY", "")).strip():
            payload = row_by_name.to_dict()
            payload["IMAGE HASH KEY"] = img_hash
            for h in HEADERS:
                payload.setdefault(h, "")
            update_row(ws, row_number, payload)
            st.info("No hash found in sheet for this file. Computed and saved IMAGE HASH KEY.")
            df = read_df(ws)
            row_by_name = find_by_filename(df, file_name)

        # Prediction
        prediction = predict_sex_from_shape(row_by_name.get("SHAPE", ""))
        if prediction:
            st.success(f"Prediction of Image: **{prediction}** ")
        else:
            st.warning("No valid SHAPE set (use 'Round' or 'Oval') → cannot predict.")

        st.markdown("**Matched Record**")
        show_record_table(row_by_name)

        if st.button("✎ Edit this record"):
            st.session_state.editing_row_number = row_number
            st.session_state.editing_defaults = {col: str(row_by_name.get(col, "")) for col in HEADERS}
            st.rerun()
        return

    # Try by HASH
    row_by_hash = find_by_hash(df, img_hash)
    if row_by_hash is not None:
        st.success("Found a match by IMAGE HASH KEY (duplicate image with different name/location).")
        row_number = int(row_by_hash["_ROW_NUMBER"])

        prediction = predict_sex_from_shape(row_by_hash.get("SHAPE", ""))
        if prediction:
            st.success(f"Prediction of Image: **{prediction}** ")
        else:
            st.warning("No valid SHAPE set (use 'Round' or 'Oval') → cannot predict.")

        st.markdown("**Matched Record**")
        show_record_table(row_by_hash)

        if st.button("✎ Edit this record"):
            st.session_state.editing_row_number = row_number
            st.session_state.editing_defaults = {col: str(row_by_hash.get(col, "")) for col in HEADERS}
            st.rerun()
        return

    # No match → create new entry
    st.warning("No match found by FILE NAME or IMAGE HASH KEY. Please create a new entry.")
    defaults = {"FILE NAME": file_name, "IMAGE HASH KEY": img_hash}
    render_create_or_edit_form(mode="create", ws=ws, df=df, defaults=defaults)



if __name__ == "__main__":
    main()
