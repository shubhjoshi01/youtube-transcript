from fastapi import FastAPI, HTTPException, Query
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound, VideoUnavailable
from youtube_transcript_api.proxies import WebshareProxyConfig
from pydantic import BaseModel, validator
from typing import Optional, List, Dict, Any
import re
import logging
from urllib.parse import urlparse, parse_qs

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="YouTube Transcript API",
    description="A FastAPI server for fetching YouTube video transcripts",
    version="1.0.0"
)

# Global YouTube Transcript API instance
ytt = YouTubeTranscriptApi()

class ProxyConfig(BaseModel):
    proxy_username: str
    proxy_password: str
    
class TranscriptRequest(BaseModel):
    video_id: str
    languages: Optional[List[str]] = ["en"]
    preserve_formatting: Optional[bool] = False
    
    @validator('video_id')
    def validate_video_id(cls, v):
        # Extract video ID from URL if full URL is provided
        if 'youtube.com' in v or 'youtu.be' in v:
            v = extract_video_id(v)
        
        # Validate video ID format
        if not re.match(r'^[a-zA-Z0-9_-]{11}$', v):
            raise ValueError('Invalid YouTube video ID format')
        return v

class TranscriptResponse(BaseModel):
    success: bool
    video_id: str
    language: Optional[str] = None
    available_languages: Optional[List[str]] = None
    transcript: Optional[List[Dict[str, Any]]] = None
    formatted_text: Optional[str] = None
    error: Optional[str] = None
    total_duration: Optional[float] = None
    word_count: Optional[int] = None

class LanguageListRequest(BaseModel):
    video_id: str
    
    @validator('video_id')
    def validate_video_id(cls, v):
        if 'youtube.com' in v or 'youtu.be' in v:
            v = extract_video_id(v)
        if not re.match(r'^[a-zA-Z0-9_-]{11}$', v):
            raise ValueError('Invalid YouTube video ID format')
        return v

def extract_video_id(url: str) -> str:
    """Extract video ID from YouTube URL"""
    if 'youtu.be/' in url:
        return url.split('youtu.be/')[-1].split('?')[0]
    elif 'youtube.com/watch' in url:
        parsed = urlparse(url)
        return parse_qs(parsed.query).get('v', [None])[0]
    elif 'youtube.com/embed/' in url:
        return url.split('embed/')[-1].split('?')[0]
    else:
        return url

def format_transcript_text(transcript: List[Dict[str, Any]]) -> str:
    """Format transcript into readable text"""
    return ' '.join([item['text'] for item in transcript])

def calculate_duration(transcript: List[Dict[str, Any]]) -> float:
    """Calculate total duration of transcript"""
    if not transcript:
        return 0.0
    last_item = transcript[-1]
    return last_item.get('start', 0) + last_item.get('duration', 0)

@app.post("/configure-proxy")
async def configure_proxy(proxy_config: ProxyConfig):
    """Configure proxy settings for YouTube Transcript API"""
    try:
        global ytt
        proxy_cfg = WebshareProxyConfig(
            proxy_username=proxy_config.proxy_username,
            proxy_password=proxy_config.proxy_password
        )
        ytt = YouTubeTranscriptApi(proxy_config=proxy_cfg)
        return {"success": True, "message": "Proxy configured successfully"}
    except Exception as e:
        logger.error(f"Failed to configure proxy: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to configure proxy: {str(e)}")

@app.post("/transcript", response_model=TranscriptResponse)
async def get_transcript(request: TranscriptRequest):
    """
    Get transcript for a YouTube video
    
    - **video_id**: YouTube video ID or full URL
    - **languages**: List of language codes to try (default: ["en"])
    - **preserve_formatting**: Whether to preserve original formatting
    """
    try:
        # Fetch transcript
        transcript_list = ytt.get_transcript(
            request.video_id, 
            languages=request.languages
        )
        
        # Get available languages for this video
        available_languages = []
        try:
            transcript_list_fetcher = ytt.list_transcripts(request.video_id)
            available_languages = [t.language_code for t in transcript_list_fetcher]
        except Exception:
            pass
        
        # Calculate statistics
        total_duration = calculate_duration(transcript_list)
        formatted_text = format_transcript_text(transcript_list)
        word_count = len(formatted_text.split())
        
        # Determine which language was actually used
        used_language = None
        if transcript_list:
            # Try to determine language from the transcript list
            try:
                transcript_list_fetcher = ytt.list_transcripts(request.video_id)
                for transcript in transcript_list_fetcher:
                    if transcript.language_code in request.languages:
                        used_language = transcript.language_code
                        break
            except Exception:
                used_language = request.languages[0] if request.languages else "unknown"
        
        return TranscriptResponse(
            success=True,
            video_id=request.video_id,
            language=used_language,
            available_languages=available_languages,
            transcript=transcript_list,
            formatted_text=formatted_text,
            total_duration=total_duration,
            word_count=word_count
        )
        
    except TranscriptsDisabled:
        return TranscriptResponse(
            success=False,
            video_id=request.video_id,
            error="Transcripts are disabled for this video"
        )
    except NoTranscriptFound:
        return TranscriptResponse(
            success=False,
            video_id=request.video_id,
            error=f"No transcript found for languages: {request.languages}"
        )
    except VideoUnavailable:
        return TranscriptResponse(
            success=False,
            video_id=request.video_id,
            error="Video is unavailable"
        )
    except Exception as e:
        logger.error(f"Unexpected error fetching transcript for {request.video_id}: {str(e)}")
        return TranscriptResponse(
            success=False,
            video_id=request.video_id,
            error=f"Unexpected error: {str(e)}"
        )

@app.get("/transcript")
async def get_transcript_get(
    video_id: str = Query(..., description="YouTube video ID or URL"),
    languages: Optional[str] = Query("en", description="Comma-separated language codes"),
    preserve_formatting: Optional[bool] = Query(False, description="Preserve original formatting")
):
    """
    GET endpoint for fetching transcripts with query parameters
    """
    language_list = [lang.strip() for lang in languages.split(',') if lang.strip()]
    
    request = TranscriptRequest(
        video_id=video_id,
        languages=language_list,
        preserve_formatting=preserve_formatting
    )
    return await get_transcript(request)

@app.post("/available-languages")
async def get_available_languages(request: LanguageListRequest):
    """
    Get list of available transcript languages for a video
    
    - **video_id**: YouTube video ID or full URL
    """
    try:
        transcript_list = ytt.list_transcripts(request.video_id)
        
        languages = []
        for transcript in transcript_list:
            lang_info = {
                "language_code": transcript.language_code,
                "language": transcript.language,
                "is_generated": transcript.is_generated,
                "is_translatable": transcript.is_translatable
            }
            languages.append(lang_info)
        
        return {
            "success": True,
            "video_id": request.video_id,
            "available_languages": languages
        }
        
    except TranscriptsDisabled:
        return {
            "success": False,
            "video_id": request.video_id,
            "error": "Transcripts are disabled for this video"
        }
    except VideoUnavailable:
        return {
            "success": False,
            "video_id": request.video_id,
            "error": "Video is unavailable"
        }
    except Exception as e:
        logger.error(f"Error getting available languages for {request.video_id}: {str(e)}")
        return {
            "success": False,
            "video_id": request.video_id,
            "error": f"Unexpected error: {str(e)}"
        }

@app.get("/available-languages")
async def get_available_languages_get(
    video_id: str = Query(..., description="YouTube video ID or URL")
):
    """
    GET endpoint for fetching available languages with query parameters
    """
    request = LanguageListRequest(video_id=video_id)
    return await get_available_languages(request)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "YouTube Transcript API"}

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "YouTube Transcript FastAPI Server is running",
        "version": "1.0.0",
        "endpoints": {
            "POST /transcript": "Main transcript endpoint with full options",
            "GET /transcript": "Simple transcript fetch with query parameters",
            "POST /available-languages": "Get available transcript languages",
            "GET /available-languages": "Get available languages with query parameters",
            "POST /configure-proxy": "Configure proxy settings",
            "GET /health": "Health check endpoint",
            "GET /docs": "Interactive API documentation"
        },
        "example_usage": {
            "simple_transcript": {
                "method": "GET",
                "url": "/transcript?video_id=VIDEO_ID&languages=en,es"
            },
            "advanced_transcript": {
                "method": "POST",
                "url": "/transcript",
                "body": {
                    "video_id": "VIDEO_ID",
                    "languages": ["en", "es", "fr"],
                    "preserve_formatting": false
                }
            },
            "available_languages": {
                "method": "GET",
                "url": "/available-languages?video_id=VIDEO_ID"
            }
        },
        "supported_formats": {
            "video_id": "11-character YouTube video ID",
            "video_url": "Full YouTube URL (youtube.com/watch?v=... or youtu.be/...)",
            "embed_url": "YouTube embed URL (youtube.com/embed/...)"
        }
    }

# Error handlers
@app.exception_handler(422)
async def validation_exception_handler(request, exc):
    return {
        "error": "Validation error",
        "details": exc.errors(),
        "message": "Please check your input parameters"
    }

@app.exception_handler(404)
async def not_found_handler(request, exc):
    return {
        "error": "Endpoint not found",
        "message": "Please check the API documentation at /docs"
    }

@app.exception_handler(500)
async def internal_error_handler(request, exc):
    logger.error(f"Internal server error: {str(exc)}")
    return {
        "error": "Internal server error",
        "message": "Please try again later"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)