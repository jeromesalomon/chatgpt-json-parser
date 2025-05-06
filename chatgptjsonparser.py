# streamlit_app.py
import streamlit as st
import pandas as pd
import json
from datetime import datetime
from io import StringIO
import base64
import pytz
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode

def convert_timestamp(ts):
    try:
        tz = pytz.timezone('Europe/Paris')
        dt = datetime.fromtimestamp(float(ts), tz=pytz.utc)
        return dt.astimezone(tz).strftime('%Y-%m-%d %H:%M:%S %Z%z')
    except:
        return ts

def clean_url(url):
    if not isinstance(url, str):
        return url
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    query.pop('utm_source', None)
    new_query = urlencode(query, doseq=True)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))

def parse_chat_json(data):
    nodes = data.get("mapping", {})
    rows = []
    for node in nodes.values():
        msg = node.get("message")
        if msg and msg.get("author", {}).get("role") == "user":
            prompt_text = msg.get("content", {}).get("parts", [""])[0]
            prompt_time = convert_timestamp(msg.get("create_time"))

            current_node = node
            assistant_response = None
            while current_node.get("children"):
                child_id = current_node["children"][0]
                child = nodes.get(child_id)
                child_msg = child.get("message") if child else None
                if child_msg and child_msg.get("author", {}).get("role") == "assistant":
                    content = child_msg.get("content", {})
                    if content.get("parts") and content["parts"][0].strip():
                        assistant_response = child
                current_node = child

            if assistant_response:
                response_msg = assistant_response["message"]
                response_text = response_msg.get("content", {}).get("parts", [""])[0]
                response_time = convert_timestamp(response_msg.get("create_time"))

                search_urls = [e.get("url") for g in response_msg.get("metadata", {}).get("search_result_groups", []) for e in g.get("entries", []) if e.get("url")]
                supporting_urls = [sw.get("url") for ref in response_msg.get("metadata", {}).get("content_references", []) if ref.get("type") == "grouped_webpages"
                                   for item in ref.get("items", []) for sw in item.get("supporting_websites", []) if sw.get("url")]
                sources_footnote = [src.get("url") for ref in response_msg.get("metadata", {}).get("content_references", []) if ref.get("type") == "sources_footnote"
                                    for src in ref.get("sources", []) if src.get("url")]

                safe_urls = list(set(response_msg.get("metadata", {}).get("safe_urls", []) + data.get("safe_urls", [])))
                blocked_urls = data.get("blocked_urls", [])

                rows.append({
                    "prompt_text": prompt_text,
                    "prompt_date_time": prompt_time,
                    "response_text": response_text,
                    "response_date_time": response_time,
                    "search_results": search_urls,
                    "sources_footnote": sources_footnote,
                    "supporting_websites": supporting_urls,
                    "safe_urls": safe_urls,
                    "blocked_urls": blocked_urls
                })

    return pd.DataFrame(rows)

def generate_csv_download(df):
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    href = f'<a href="data:file/csv;base64,{b64}" download="chat_data.csv">Download CSV</a>'
    return href

# Streamlit UI
st.title("Chat Export JSON Viewer")
json_input = st.text_area("Paste your Chat JSON export here", height=300)

if st.button("Parse JSON"):
    try:
        parsed_json = json.loads(json_input)
        df = parse_chat_json(parsed_json)

        if df.empty:
            st.warning("No valid prompt-response pairs found.")
        else:
            st.dataframe(df)
            st.markdown(generate_csv_download(df), unsafe_allow_html=True)
    except Exception as e:
        st.error(f"Invalid JSON. Error: {e}")