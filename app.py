
'''
uvicorn app:app --reload
'''

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
import os
import json
import asyncio
from datetime import datetime
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from typing import Optional, Dict, Any
from pydantic import BaseModel
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 환경 변수 로드
load_dotenv()

app = FastAPI()

# 정적 파일과 템플릿 설정
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# S3 클라이언트 설정
s3 = boto3.client('s3',
    endpoint_url=os.getenv('NCP_ENDPOINT_URL'),
    aws_access_key_id=os.getenv('NCP_ACCESS_KEY'),
    aws_secret_access_key=os.getenv('NCP_SECRET_KEY')
)
BUCKET_NAME = os.getenv('NCP_BUCKET_NAME')

class AudioURL(BaseModel):
    url: str

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/get-initial-data")
async def get_initial_data():
    try:
        date = datetime.now().strftime("%Y-%m-%d")
        stt_key = f"results/{date}.json"
        
        logger.info(f"Attempting to fetch data from {stt_key}")
        response = s3.get_object(Bucket=BUCKET_NAME, Key=stt_key)
        data = json.loads(response['Body'].read().decode('utf-8'))
        logger.info(f"Successfully fetched data: {data}")
        return JSONResponse(content=data)
    except ClientError as e:
        logger.error(f"ClientError occurred: {str(e)}")
        if e.response['Error']['Code'] == 'NoSuchKey':
            # 파일이 없을 경우 빈 배열 반환
            return JSONResponse(content=[])
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

async def generate_sse_events():
    last_timestamp: Optional[str] = None
    while True:
        try:
            date = datetime.now().strftime("%Y-%m-%d")
            stt_key = f"results/{date}.json"
            
            logger.debug(f"Checking for updates in {stt_key}")
            response = s3.get_object(Bucket=BUCKET_NAME, Key=stt_key)
            data = json.loads(response['Body'].read().decode('utf-8'))

            if data and (last_timestamp is None or data[-1]["timestamp"] != last_timestamp):
                last_timestamp = data[-1]["timestamp"]
                logger.info(f"New data found: {data[-1]}")
                yield f"data: {json.dumps(data[-1])}\n\n"
        except ClientError as e:
            if e.response['Error']['Code'] != 'NoSuchKey':
                logger.error(f"S3 error: {str(e)}")
        except Exception as e:
            logger.error(f"Stream error: {str(e)}")
        
        await asyncio.sleep(1)

@app.get("/stream")
async def stream():
    return StreamingResponse(
        generate_sse_events(),
        media_type="text/event-stream"
    )

@app.get("/audio/{filename:path}", response_model=AudioURL)
async def serve_audio(filename: str):
    try:
        # S3에서 임시 URL 생성
        url = s3.generate_presigned_url('get_object',
            Params={'Bucket': BUCKET_NAME, 'Key': f"audio/{filename}"},
            ExpiresIn=3600
        )
        return AudioURL(url=url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 서버 상태 체크용 엔드포인트 (UptimeRobot용)
@app.get("/health")
async def health_check():
    return {"status": "healthy"}
