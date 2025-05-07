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

def group_urls_for_copy(df):
    groups = {
        "Search results": [],
        "Main citations (sources footnote)": [],
        "Additional citations (supporting websites)": [],
        "Safe URLs": [],
        "Blocked URLs": [],
        "Relevant URLs": [],
        "Not relevant enough URLs": []
    }

    for _, row in df.iterrows():
        footnotes = row.get('sources_footnote', [])
        supporting = row.get('supporting_websites', [])
        search = row.get('search_results', [])
        blocked = row.get('blocked_urls', [])
        safe = row.get('safe_urls', [])

        relevant_set = set(clean_url(url) for url in footnotes + supporting)
        search_set = set(clean_url(url) for url in search)
        not_relevant = sorted(search_set - relevant_set)

        groups["Search results"].extend(search)
        groups["Main citations (sources footnote)"].extend(footnotes)
        groups["Additional citations (supporting websites)"].extend(supporting)
        groups["Safe URLs"].extend(safe)
        groups["Blocked URLs"].extend(blocked)
        groups["Relevant URLs"].extend(relevant_set)
        groups["Not relevant enough URLs"].extend(not_relevant)

    # Deduplicate all groups
    for key in groups:
        groups[key] = sorted(set(groups[key]))

    return groups

# Streamlit UI
st.title("ChatGPT JSON conversation parser")
st.markdown(
    """
    <div style='display: flex; align-items: center; justify-content: space-between;'>
        <a href="https://www.oncrawl.com/events/how-to-appear-in-chatgpt-practical-seo-strategies-for-ai-visibility/" target="_blank" style="text-decoration: none; font-size: 16px;">
        Watch the tutorial on 
        </a>
        Built by <a href="https://www.linkedin.com/in/jeromesalomon/" target="_blank" style="text-decoration: none; font-size: 16px;">
        JS</a> | SEO @ <a href="https://www.oncrawl.com/" target="_blank" style="text-decoration: none; font-size: 16px;">Oncrawl
        </a>
        </div>
    <div style='display: flex; align-items: center;'>
    1) Open a ChatGPT conversation (with Search Activated) and find the json file:
        <img src="https://raw.githubusercontent.com/jeromesalomon/chatgpt-json-parser/refs/heads/main/chatgptjson.jpeg" width="100%">
    </div>
    </br>
    """,
    unsafe_allow_html=True
)
json_input = st.text_area("2) Paste your ChatGPT JSON here", height=300)

if st.button("Parse JSON"):
    try:
        parsed_json = json.loads(json_input)
        df = parse_chat_json(parsed_json)

        if df.empty:
            st.warning("No valid prompt-response pairs found.")
        else:
            st.dataframe(df)
            st.markdown(generate_csv_download(df), unsafe_allow_html=True)

            # Display grouped URLs with copy-paste option
            st.subheader("Grouped URLs")

            url_groups = group_urls_for_copy(df)
            for label, urls in url_groups.items():
                with st.expander(label):
                    st.text_area(f"","\n".join(urls), height=300)
    except Exception as e:
        st.error(f"Invalid JSON. Error: {e}")
