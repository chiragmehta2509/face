import streamlit as st
import face_recognition
import numpy as np
from PIL import Image
import io
import os
import json
import pickle
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account

# ─────────────────────────────────────────────
#  PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="📸 Face Finder",
    page_icon="🔍",
    layout="centered"
)

st.title("📸 Face Finder")
st.markdown("Take a selfie and find your photos from the Drive folder!")

# ─────────────────────────────────────────────
#  CONSTANTS – edit these two lines
# ─────────────────────────────────────────────
DRIVE_FOLDER_ID = "0B_yhaGhzavnuS0twM2xQNUdwTDQ"   # <-- paste your folder ID here
ENCODINGS_CACHE = "face_encodings_cache.pkl"       # cache so Drive isn't re-scanned every time


# ─────────────────────────────────────────────
#  GOOGLE DRIVE CONNECTION
# ─────────────────────────────────────────────
@st.cache_resource(show_spinner="Connecting to Google Drive…")
def get_drive_service():
    """Build Drive service from secrets or local credentials.json"""
    try:
        # Streamlit Cloud: store JSON key in st.secrets["google_service_account"]
        creds_dict = dict(st.secrets["google_service_account"])
        creds = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=["https://www.googleapis.com/auth/drive.readonly"]
        )
    except Exception:
        # Local: place credentials.json in the same folder as app.py
        if not os.path.exists("credentials.json"):
            st.error("❌ credentials.json not found. See setup instructions in README.")
            st.stop()
        creds = service_account.Credentials.from_service_account_file(
            "credentials.json",
            scopes=["https://www.googleapis.com/auth/drive.readonly"]
        )
    return build("drive", "v3", credentials=creds)


def list_images_in_folder(service, folder_id):
    """Return list of (file_id, file_name) for images in the folder (recursive)."""
    image_mime_types = [
        "image/jpeg", "image/png", "image/webp",
        "image/heic", "image/heif", "image/gif"
    ]
    mime_query = " or ".join([f"mimeType='{m}'" for m in image_mime_types])
    query = f"('{folder_id}' in parents) and ({mime_query}) and trashed=false"

    files = []
    page_token = None
    while True:
        resp = service.files().list(
            q=query,
            fields="nextPageToken, files(id, name)",
            pageToken=page_token,
            pageSize=100
        ).execute()
        files.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return files


def download_image(service, file_id) -> Image.Image | None:
    """Download an image from Drive and return as PIL Image."""
    try:
        request = service.files().get_media(fileId=file_id)
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        buf.seek(0)
        return Image.open(buf).convert("RGB")
    except Exception:
        return None


# ─────────────────────────────────────────────
#  FACE ENCODING HELPERS
# ─────────────────────────────────────────────
def pil_to_rgb_array(img: Image.Image) -> np.ndarray:
    return np.array(img.convert("RGB"))


def encode_face(img: Image.Image):
    """Return first face encoding found in image, or None."""
    arr = pil_to_rgb_array(img)
    encs = face_recognition.face_encodings(arr)
    return encs[0] if encs else None


@st.cache_data(show_spinner=False)
def load_or_build_encodings(_service, folder_id):
    """
    Load encodings from cache file if it exists,
    otherwise scan Drive folder and build + save the cache.
    Returns list of {"file_id", "name", "encoding"} dicts.
    """
    if os.path.exists(ENCODINGS_CACHE):
        with open(ENCODINGS_CACHE, "rb") as f:
            return pickle.load(f)

    files = list_images_in_folder(_service, folder_id)
    if not files:
        return []

    progress = st.progress(0, text="Scanning Drive photos…")
    records = []
    for i, file in enumerate(files):
        img = download_image(_service, file["id"])
        if img:
            enc = encode_face(img)
            if enc is not None:
                records.append({
                    "file_id": file["id"],
                    "name": file["name"],
                    "encoding": enc,
                    "thumbnail": img.resize((200, 200))
                })
        progress.progress((i + 1) / len(files), text=f"Scanning {i+1}/{len(files)} photos…")
    progress.empty()

    with open(ENCODINGS_CACHE, "wb") as f:
        pickle.dump(records, f)

    return records


def find_matches(selfie_encoding, records, tolerance=0.50):
    """Return records whose face matches the selfie encoding."""
    matches = []
    for rec in records:
        dist = face_recognition.face_distance([rec["encoding"]], selfie_encoding)[0]
        if dist <= tolerance:
            matches.append({**rec, "confidence": round((1 - dist) * 100, 1)})
    return sorted(matches, key=lambda x: -x["confidence"])


# ─────────────────────────────────────────────
#  SIDEBAR – settings & cache management
# ─────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Settings")
    tolerance = st.slider(
        "Match sensitivity",
        min_value=0.30, max_value=0.70, value=0.50, step=0.05,
        help="Lower = stricter matching. 0.50 is a good default."
    )
    st.markdown("---")
    if st.button("🔄 Rescan Drive (clear cache)"):
        if os.path.exists(ENCODINGS_CACHE):
            os.remove(ENCODINGS_CACHE)
            st.cache_data.clear()
        st.success("Cache cleared! Reload the page to rescan.")
    st.markdown("---")
    st.markdown("**How to use**")
    st.markdown("1. Allow camera access\n2. Take a clear selfie\n3. Click **Find My Photos**")


# ─────────────────────────────────────────────
#  MAIN UI
# ─────────────────────────────────────────────
service = get_drive_service()

# Load / build encodings once
with st.spinner("Loading Drive photo index… (first run may take a few minutes)"):
    records = load_or_build_encodings(service, DRIVE_FOLDER_ID)

if not records:
    st.warning("⚠️ No faces found in the Drive folder. Check your DRIVE_FOLDER_ID and make sure the folder has photos with visible faces.")
    st.stop()

st.success(f"✅ {len(records)} faces indexed from Drive folder")

# Camera input (works on mobile too)
st.markdown("### 📷 Take a Selfie")
camera_image = st.camera_input("Position your face in the frame and click the capture button")

if camera_image:
    selfie = Image.open(camera_image).convert("RGB")
    selfie_enc = encode_face(selfie)

    if selfie_enc is None:
        st.error("😕 No face detected in your photo. Please try again with better lighting and face the camera directly.")
    else:
        st.success("✅ Face detected!")

        if st.button("🔍 Find My Photos", type="primary", use_container_width=True):
            with st.spinner("Searching for your photos…"):
                matches = find_matches(selfie_enc, records, tolerance)

            if not matches:
                st.warning("🤷 No matching photos found. Try lowering the sensitivity in the sidebar.")
            else:
                st.markdown(f"### 🎉 Found {len(matches)} matching photo(s)!")

                # Display in a grid
                cols_per_row = 3
                for row_start in range(0, len(matches), cols_per_row):
                    cols = st.columns(cols_per_row)
                    for col, match in zip(cols, matches[row_start:row_start + cols_per_row]):
                        with col:
                            st.image(match["thumbnail"], use_container_width=True)
                            st.caption(f"**{match['name']}**\n{match['confidence']}% match")

                            # Download full-res image button
                            full_img = download_image(service, match["file_id"])
                            if full_img:
                                buf = io.BytesIO()
                                full_img.save(buf, format="JPEG")
                                st.download_button(
                                    label="⬇️ Download",
                                    data=buf.getvalue(),
                                    file_name=match["name"],
                                    mime="image/jpeg",
                                    use_container_width=True
                                )
