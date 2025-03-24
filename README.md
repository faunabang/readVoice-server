uv venv .venv --python 3.8
.venv/Scripts/activate
uv pip install -r requirements.txt
uvicorn app:app --reload
