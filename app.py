import streamlit as st
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound, VideoUnavailable
import re
from urllib.parse import urlparse, parse_qs

st.set_page_config(page_title="YouTube Transcript Fetcher", page_icon="🎬", layout="centered")
st.title("🎬 YouTube Transcript Fetcher")
st.markdown("""
Fetch and analyze YouTube video transcripts easily. Enter a YouTube URL or video ID, select language, and get the transcript instantly!
""")

# Helper functions (from main.py)
def extract_video_id(url: str) -> str:
    if 'youtu.be/' in url:
        return url.split('youtu.be/')[-1].split('?')[0]
    elif 'youtube.com/watch' in url:
        parsed = urlparse(url)
        return parse_qs(parsed.query).get('v', [None])[0]
    elif 'youtube.com/embed/' in url:
        return url.split('embed/')[-1].split('?')[0]
    else:
        return url

def format_transcript_text(transcript):
    return ' '.join([item['text'] for item in transcript])

def calculate_duration(transcript):
    if not transcript:
        return 0.0
    last_item = transcript[-1]
    return last_item.get('start', 0) + last_item.get('duration', 0)

# UI Elements
with st.form("transcript_form"):
    video_input = st.text_input("YouTube Video URL or ID", "")
    language_input = st.text_input("Languages (comma-separated, e.g. en,hi,es)", "en")
    submit = st.form_submit_button("Get Transcript")

if submit:
    if not video_input:
        st.error("Please enter a YouTube video URL or ID.")
    else:
        # Extract and validate video ID
        try:
            video_id = extract_video_id(video_input)
            if not re.match(r'^[a-zA-Z0-9_-]{11}$', video_id):
                raise ValueError('Invalid YouTube video ID format')
        except Exception as e:
            st.error(f"Error: {e}")
            st.stop()

        languages = [lang.strip() for lang in language_input.split(',') if lang.strip()]
        ytt = YouTubeTranscriptApi()
        try:
            transcript = ytt.get_transcript(video_id, languages=languages)
            formatted_text = format_transcript_text(transcript)
            total_duration = calculate_duration(transcript)
            word_count = len(formatted_text.split())

            st.success("Transcript fetched successfully!")
            st.markdown(f"**Word Count:** {word_count}")
            st.markdown(f"**Total Duration:** {total_duration:.2f} seconds")
            st.markdown("---")
            st.markdown("#### Transcript:")
            st.write(formatted_text)
            st.download_button("Download Transcript as TXT", formatted_text, file_name=f"{video_id}_transcript.txt")
        except TranscriptsDisabled:
            st.error("Transcripts are disabled for this video.")
        except NoTranscriptFound:
            st.error(f"No transcript found for languages: {languages}")
        except VideoUnavailable:
            st.error("Video is unavailable.")
        except Exception as e:
            st.error(f"Unexpected error: {e}")

st.markdown("---")
st.markdown("""
<small>Made with ❤️ using [Streamlit](https://streamlit.io/) and [youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api)</small>""", unsafe_allow_html=True) 