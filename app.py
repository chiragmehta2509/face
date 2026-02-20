import streamlit as st
import numpy as np
from PIL import Image
import io
import os
import pickle
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
from deepface import DeepFace

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
#  CONSTANTS — paste your Drive folder ID below
# ─────────────────────────────────────────────
DRIVE_FOLDER_ID = "0B_yhaGhzavnuS0twM2xQNUdwTDQ"
ENCODINGS_CACHE = "/tmp/face_encodings_cache.pkl"
MODEL_NAME      = "Facenet"
DETECTOR        = "opencv"


# ─────────────────────────────────────────────
#  GOOGLE DRIVE CONNECTION
# ─────────────────────────────────────────────
@st.cache_resource(show_spinner="Connecting to Google Drive…")
def get_drive_service():
    SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

    # Try Streamlit Cloud secrets first
    if "google_service_account" in st.secrets:
        creds = service_account.Credentials.from_service_account_info(
            st.secrets["google_service_account"],
            scopes=SCOPES
        )
        return build("drive", "v3", credentials=creds)

    # Fallback to local credentials.json
    if os.path.exists("credentials.json"):
        creds = service_account.Credentials.from_service_account_file(
            "credentials.json",
            scopes=SCOPES
        )
        return build("drive", "v3", credentials=creds)

    # Neither found — show clear instructions
    st.error("""
    ❌ Google credentials not found!

    **If you are on Streamlit Cloud:**
    - Go to your app → ⋮ menu → Settings → Secrets
    - Make sure your secrets start with `[google_service_account]`
    - Click Save and wait for the app to restart

    **If running locally:**
    - Place `credentials.json` in the same folder as `app.py`
    """)
    st.stop()


def list_images_in_folder(service, folder_id):
    mime_types = ["image/jpeg", "image/png", "image/webp", "image/heic"]
    mime_query = " or ".join([f"mimeType='{m}'" for m in mime_types])
    query = f"('{folder_id}' in parents) and ({mime_query}) and trashed=false"
    files, page_token = [], None
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


def download_image(service, file_id):
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


def get_embedding(img: Image.Image):
    try:
        path = "/tmp/face_input.jpg"
        img.save(path, format="JPEG")
        result = DeepFace.represent(
            img_path=path,
            model_name=MODEL_NAME,
            detector_backend=DETECTOR,
            enforce_detection=True
        )
        return np.array(result[0]["embedding"])
    except Exception:
        return None


@st.cache_data(show_spinner=False)
def load_or_build_encodings(_service, folder_id):
    if os.path.exists(ENCODINGS_CACHE):
        with open(ENCODINGS_CACHE, "rb") as f:
            return pickle.load(f)

    files = list_images_in_folder(_service, folder_id)
    if not files:
        return []

    progress = st.progress(0, text="Scanning Drive photos for faces…")
    records = []
    for i, file in enumerate(files):
        img = download_image(_service, file["id"])
        if img:
            emb = get_embedding(img)
            if emb is not None:
                records.append({
                    "file_id":   file["id"],
                    "name":      file["name"],
                    "embedding": emb,
                    "thumbnail": img.resize((200, 200))
                })
        progress.progress((i + 1) / len(files), text=f"Scanning {i+1}/{len(files)} photos…")
    progress.empty()

    with open(ENCODINGS_CACHE, "wb") as f:
        pickle.dump(records, f)

    return records


def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def find_matches(selfie_emb, records, threshold=0.70):
    matches = []
    for rec in records:
        sim = cosine_similarity(selfie_emb, rec["embedding"])
        if sim >= threshold:
            matches.append({**rec, "confidence": round(sim * 100, 1)})
    return sorted(matches, key=lambda x: -x["confidence"])


# ─────────────────────────────────────────────
#  SIDEBAR
# ─────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Settings")
    threshold = st.slider(
        "Match sensitivity",
        min_value=0.50, max_value=0.95, value=0.70, step=0.05,
        help="Higher = stricter. Lower = more results."
    )
    st.markdown("---")
    if st.button("🔄 Rescan Drive (clear cache)"):
        if os.path.exists(ENCODINGS_CACHE):
            os.remove(ENCODINGS_CACHE)
            st.cache_data.clear()
        st.success("Cache cleared! Reload the page to rescan.")
    st.markdown("---")
    st.markdown("**How to use**\n1. Allow camera\n2. Take a clear selfie\n3. Click **Find My Photos**")


# ─────────────────────────────────────────────
#  MAIN UI
# ─────────────────────────────────────────────
service = get_drive_service()

with st.spinner("Loading photo index… (first run scans Drive — takes a few minutes)"):
    records = load_or_build_encodings(service, DRIVE_FOLDER_ID)

if not records:
    st.warning("⚠️ No faces found in the Drive folder. Check DRIVE_FOLDER_ID in app.py.")
    st.stop()

st.success(f"✅ {len(records)} faces indexed from your Drive folder")

st.markdown("### 📷 Take a Selfie")
camera_image = st.camera_input("Position your face clearly and click capture")

if camera_image:
    selfie = Image.open(camera_image).convert("RGB")
    with st.spinner("Detecting your face…"):
        selfie_emb = get_embedding(selfie)

    if selfie_emb is None:
        st.error("😕 No face detected. Try better lighting and face the camera directly.")
    else:
        st.success("✅ Face detected!")
        if st.button("🔍 Find My Photos", type="primary", use_container_width=True):
            with st.spinner("Searching through all photos…"):
                matches = find_matches(selfie_emb, records, threshold)

            if not matches:
                st.warning("🤷 No matching photos found. Try lowering the sensitivity in the sidebar.")
            else:
                st.markdown(f"### 🎉 Found {len(matches)} matching photo(s)!")
                cols_per_row = 3
                for row_start in range(0, len(matches), cols_per_row):
                    cols = st.columns(cols_per_row)
                    for col, match in zip(cols, matches[row_start:row_start + cols_per_row]):
                        with col:
                            st.image(match["thumbnail"], use_container_width=True)
                            st.caption(f"**{match['name']}**\n{match['confidence']}% match")
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
