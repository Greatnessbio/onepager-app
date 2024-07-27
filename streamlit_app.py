import streamlit as st
import requests
import json
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import time
import os
import difflib

# Initialize session state
if 'content' not in st.session_state:
    st.session_state.content = ""
if 'enhanced_content' not in st.session_state:
    st.session_state.enhanced_content = ""
if 'audit' not in st.session_state:
    st.session_state.audit = ""
if 'summary' not in st.session_state:
    st.session_state.summary = ""

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

def enhance_content_single_pass(audit, content):
    OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
    if not OPENROUTER_API_KEY:
        st.error("OpenRouter API key not found. Please set the OPENROUTER_API_KEY environment variable.")
        return None

    prompt = f"""Analyze the following keyword audit and web page content, then create an enhanced version of the content based on the audit findings. Follow these steps:

1. Keyword audit:
<keyword_audit>
{audit}
</keyword_audit>

2. Original web page content:
<original_content>
{content}
</original_content>

3. Analyze the keyword audit and the original content.

4. Provide your response in two parts:
   a) A summary of your analysis and recommended changes (max 300 words).
   b) The full enhanced content, incorporating your recommendations.

Ensure that your enhanced content:
- Naturally incorporates more keywords from the audit
- Improves the overall quality and relevance of the content
- Maintains the original tone and style of the page
- Does not overstuff keywords or make the content sound unnatural

Format your response as follows:

<summary>
Your analysis and recommendations here (max 300 words)
</summary>

<enhanced_content>
Your full enhanced content here, ready to be pasted into WordPress
</enhanced_content>

Remember, the enhanced content should be the final version, without any markup or explanatory notes."""

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

def enhance_content_multi_step(audit, content):
    OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
    if not OPENROUTER_API_KEY:
        st.error("OpenRouter API key not found. Please set the OPENROUTER_API_KEY environment variable.")
        return None

    steps = [
        "Analyze the keyword audit and identify key themes and opportunities.",
        "Review the original content and suggest high-level improvements based on the audit.",
        "Enhance the content structure and headings to better incorporate key themes.",
        "Improve the introduction and conclusion to better align with SEO goals.",
        "Enhance the body content to naturally incorporate more keywords and improve relevance.",
        "Final review and refinement of the enhanced content."
    ]

    results = []
    current_content = content

    for i, step in enumerate(steps):
        prompt = f"""Step {i+1} of 6: {step}

Keyword audit:
<keyword_audit>
{audit}
</keyword_audit>

Current content:
<current_content>
{current_content}
</current_content>

Provide your response for this step:

<step_response>
Your response here
</step_response>

<updated_content>
Updated content based on your changes (if applicable)
</updated_content>
"""

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
            result = response.json()['choices'][0]['message']['content']
            results.append(result)
            
            step_response = result.split('<step_response>')[1].split('</step_response>')[0].strip()
            updated_content = result.split('<updated_content>')[1].split('</updated_content>')[0].strip()
            
            if updated_content:
                current_content = updated_content
            
            yield i+1, step_response, current_content
        else:
            st.error(f"Error from OpenRouter API: {response.status_code} - {response.text}")
            return

def extract_sections(text):
    summary_start = text.find("<summary>")
    summary_end = text.find("</summary>")
    enhanced_start = text.find("<enhanced_content>")
    enhanced_end = text.find("</enhanced_content>")
    
    summary = text[summary_start+9:summary_end].strip()
    enhanced_content = text[enhanced_start+18:enhanced_end].strip()
    
    return summary, enhanced_content

def highlight_diff(original, enhanced):
    d = difflib.Differ()
    diff = list(d.compare(original.splitlines(), enhanced.splitlines()))
    
    highlighted = []
    for line in diff:
        if line.startswith('+ '):
            highlighted.append(f'<span style="background-color: #aaffaa;">{line[2:]}</span>')
        elif line.startswith('- '):
            highlighted.append(f'<span style="background-color: #ffaaaa;">{line[2:]}</span>')
        elif line.startswith('  '):
            highlighted.append(line[2:])
    
    return '<br>'.join(highlighted)

def main():
    st.title('Web Scraper and SEO Content Enhancer')

    if check_password():
        st.success("Logged in successfully!")

        url = st.text_input('Enter URL to scrape (including http:// or https://):')
        st.session_state.audit = st.text_area('Paste your keyword audit here:', height=200)
        
        process_type = st.radio("Choose process type:", ("Single Pass", "Multi-step"))
        
        if st.button('Fetch and Enhance Content'):
            if url and st.session_state.audit:
                with st.spinner('Fetching content...'):
                    st.session_state.content = get_jina_reader_content(url)
                
                if st.session_state.content and not st.session_state.content.startswith("Failed to fetch content"):
                    st.success("Content fetched successfully!")
                    
                    if process_type == "Single Pass":
                        with st.spinner('Enhancing content...'):
                            enhanced_result = enhance_content_single_pass(st.session_state.audit, st.session_state.content)
                        
                        if enhanced_result:
                            st.success("Content enhanced successfully!")
                            summary, enhanced_content = extract_sections(enhanced_result)
                            st.session_state.summary = summary
                            st.session_state.enhanced_content = enhanced_content
                        else:
                            st.error("Failed to enhance content.")
                    else:  # Multi-step process
                        st.write("Enhancing content in multiple steps:")
                        progress_bar = st.progress(0)
                        for i, step_response, current_content in enhance_content_multi_step(st.session_state.audit, st.session_state.content):
                            progress_bar.progress(i/6)
                            st.write(f"Step {i}: {step_response}")
                            st.session_state.enhanced_content = current_content
                        st.success("Content enhancement completed!")
                else:
                    st.error(st.session_state.content)
            else:
                st.warning('Please enter a URL and paste the keyword audit')
        
        if st.session_state.content:
            st.subheader("Original Content:")
            st.text_area("Full content", st.session_state.content, height=200)
        
        if 'summary' in st.session_state and st.session_state.summary:
            st.subheader("Summary of Changes:")
            st.write(st.session_state.summary)
        
        if 'enhanced_content' in st.session_state and st.session_state.enhanced_content:
            st.subheader("Enhanced Content:")
            st.text_area("Enhanced content (ready for WordPress)", st.session_state.enhanced_content, height=400)
            
            st.subheader("Highlighted Changes:")
            highlighted_diff = highlight_diff(st.session_state.content, st.session_state.enhanced_content)
            st.markdown(highlighted_diff, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
