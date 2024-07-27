import streamlit as st
import requests
import json
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import time
import os

# Initialize session state
if 'content' not in st.session_state:
    st.session_state.content = ""
if 'enhanced_content' not in st.session_state:
    st.session_state.enhanced_content = ""
if 'audit' not in st.session_state:
    st.session_state.audit = ""

# User agent to mimic a browser
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# Create a retry strategy
retry_strategy = Retry(
    total=3,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["HEAD", "GET", "OPTIONS"],
    backoff_factor=1
)
adapter = HTTPAdapter(max_retries=retry_strategy)
http = requests.Session()
http.mount("https://", adapter)
http.mount("http://", adapter)

def check_password():
    """Returns `True` if the user had the correct password."""
    def password_entered():
        if st.session_state["password"] == st.secrets["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input(
            "Password", type="password", on_change=password_entered, key="password"
        )
        return False
    elif not st.session_state["password_correct"]:
        st.text_input(
            "Password", type="password", on_change=password_entered, key="password"
        )
        st.error("😕 Password incorrect")
        return False
    else:
        return True

def get_jina_reader_content(url):
    jina_url = f"https://r.jina.ai/{url}"
    try:
        response = http.get(jina_url, headers=HEADERS)
        response.raise_for_status()
        time.sleep(3)  # 3-second delay between requests
        return response.text
    except requests.exceptions.RequestException as e:
        return f"Failed to fetch content: {str(e)}"

def enhance_content(audit, content):
    OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
    if not OPENROUTER_API_KEY:
        st.error("OpenRouter API key not found. Please set the OPENROUTER_API_KEY environment variable.")
        return None

    prompt = f"""You are tasked with analyzing a keyword audit and a scraped web page, then creating an enhanced version of the page content based on the audit findings. Follow these steps carefully:

1. First, you will be provided with a keyword audit. This audit contains important keywords and phrases relevant to the topic of the web page.

<keyword_audit>
{audit}
</keyword_audit>

2. Next, you will be given the content of a scraped web page.

<scraped_page_content>
{content}
</scraped_page_content>

3. Analyze the keyword audit:
   - Identify the most important keywords and phrases
   - Note their frequency and relevance to the topic
   - Determine if there are any keyword gaps or opportunities for improvement

4. Analyze the scraped page content:
   - Assess how well the current content incorporates the keywords from the audit
   - Identify areas where the content could be improved or expanded
   - Look for opportunities to naturally integrate more keywords

5. Create a marked-up version of the page content:
   - Use XML tags to indicate your proposed changes
   - Use <add></add> tags for new content you suggest adding
   - Use <remove></remove> tags for content you suggest removing
   - Use <modify></modify> tags for content you suggest changing, with the proposed change inside the tags
   - Ensure that your changes:
     a) Naturally incorporate more keywords from the audit
     b) Improve the overall quality and relevance of the content
     c) Maintain the original tone and style of the page
     d) Do not overstuff keywords or make the content sound unnatural

6. Provide your enhanced version of the page content inside <enhanced_content> tags. Include a brief explanation of your changes and reasoning before the enhanced content.

Remember to maintain the overall structure and purpose of the original page while making your enhancements. Your goal is to improve the page's SEO performance without sacrificing readability or user experience."""

    response = requests.post(
        url="https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "anthropic/claude-3.5-sonnet",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant that enhances web content based on SEO audits."},
                {"role": "user", "content": prompt}
            ]
        }
    )
    
    if response.status_code == 200:
        return response.json()['choices'][0]['message']['content']
    else:
        st.error(f"Error from OpenRouter API: {response.status_code} - {response.text}")
        return None

def main():
    st.title('Web Scraper and SEO Content Enhancer')

    if check_password():
        st.success("Logged in successfully!")

        url = st.text_input('Enter URL to scrape (including http:// or https://):')
        st.session_state.audit = st.text_area('Paste your keyword audit here:', height=200)
        
        if st.button('Fetch and Enhance Content'):
            if url and st.session_state.audit:
                with st.spinner('Fetching content...'):
                    st.session_state.content = get_jina_reader_content(url)
                
                if st.session_state.content and not st.session_state.content.startswith("Failed to fetch content"):
                    st.success("Content fetched successfully!")
                    with st.spinner('Enhancing content...'):
                        st.session_state.enhanced_content = enhance_content(st.session_state.audit, st.session_state.content)
                    
                    if st.session_state.enhanced_content:
                        st.success("Content enhanced successfully!")
                    else:
                        st.error("Failed to enhance content.")
                else:
                    st.error(st.session_state.content)
            else:
                st.warning('Please enter a URL and paste the keyword audit')
        
        if st.session_state.content:
            st.subheader("Scraped Content:")
            st.text_area("Full content", st.session_state.content, height=200)
        
        if st.session_state.enhanced_content:
            st.subheader("Enhanced Content:")
            st.write(st.session_state.enhanced_content)

if __name__ == "__main__":
    main()
