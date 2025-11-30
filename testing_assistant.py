from typing import TypedDict, Optional, List
from langgraph.graph import StateGraph, START, END
from langchain.chat_models import init_chat_model
from langchain_core.messages import (
    AnyMessage,
    SystemMessage,
    HumanMessage,
    AIMessage,
)
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import os
import streamlit as st
from pypdf import PdfReader

# =======================
# 0. 环境 & LLM 初始化
# =======================
load_dotenv()

# First, try loading from local env or Streamlit secrets
env_key = os.getenv("OPENAI_API_KEY") or st.secrets.get("OPENAI_API_KEY", None)

if env_key:
    # local dev OR Streamlit secrets exist → use them
    os.environ["OPENAI_API_KEY"] = env_key
else:
    # Otherwise → require user to enter their own key (for public deployment)
    st.sidebar.header("🔑 API Key Required")
    user_key = st.sidebar.text_input(
        "Enter your OpenAI API Key",
        type="password",
        placeholder="sk-...",
    )
    if not user_key:
        st.sidebar.warning("Please enter your API key to start.")
        st.stop()

    # Set key for the session
    os.environ["OPENAI_API_KEY"] = user_key

CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4.1-mini")
MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "openai")
CHAT_TEMPERATURE = float(os.getenv("CHAT_TEMPERATURE", "0.4"))

llm = init_chat_model(
    CHAT_MODEL,
    model_provider=MODEL_PROVIDER,
    temperature=CHAT_TEMPERATURE,
)

# =======================
# 1. Pydantic 模型（分类）
# =======================

class ClassifyAgentSchema(BaseModel):
    uses_intend: str = Field(
        description=(
            "One of: "
            '"generate_test_scenario", "get_info", "novelty_radar", '
            '"challenge_scenario", "reviewer", "bug_logger", "analogy_coach"'
        )
    )

# =======================
# 2. LangGraph 状态
# =======================

class State(TypedDict):
    messages: List[AnyMessage]
    user_state: Optional[str]
    file_context: Optional[str]

# =======================
# 3. System Prompts
# =======================

CLASSIFY_SYSTEM_PROMPT = """
Task:
Classify the user’s intent into one of the following categories:

- "generate_test_scenario"
- "get_info"
- "novelty_radar"
- "challenge_scenario"
- "reviewer"
- "bug_logger"
- "analogy_coach"

Constraints:
1. If the user explicitly tags or mentions an agent name (e.g. @novelty_radar),
   prioritise the tagged agent.
2. "analogy_coach" should be chosen when the user:
   - asks for analogies, metaphors, or examples from other domains,
   - requests a different perspective or new way of thinking,
   - expresses being stuck and wants inspiration from another field.
3. "novelty_radar" is for requests about what to explore next inside the product,
   such as gaps, coverage, or further directions.
4. "challenge_scenario" is for playful, bold, or surprising test prompts,
   usually phrased casually (e.g., “give me something crazy to try”).
5. "generate_test_scenario" is for creating or modifying actual test scenarios.
6. "reviewer" is for summarising progress or asking what has been done so far.
7. "bug_logger" is for recording bugs or issues the user reports.
8. "get_info" is for general questions or meta-level requests not belonging
   to any of the categories above.

Output:
Return only: uses_intend = "<category>"
"""

TEST_SCENARIO_PROMPT = """
### ROLE
You are a strict test scenario generator. You MUST generate exactly THREE
(UNLESS the user requests a certain amount) test scenarios for exploratory testing.

You may use:
- the conversation, and
- any uploaded document content (requirements, logs, specs) if available.

### ABSOLUTE RULES (NON-NEGOTIABLE)
- You MUST output test scenarios.
- You MUST NOT output summaries.
- You MUST NOT output JSON.
- You MUST NOT ask questions.
- You MUST NOT say “let me know”.
- You MUST NOT acknowledge the input.
- You MUST NOT output assistant-style chit-chat.
- You MUST give a hint, encouraging the tester to explore using a related testing strategy. 

### REQUIRED OUTPUT FORMAT (repeat for each scenario):

Scenario Title: <short title>

Preconditions:
- <one or two bullets, or "None">

Steps:
1. <step>
2. <step>
3. <step>

Expected Result:
- <one sentence>

Hint:
- <strategy that may be practical> (The tone must be encouraging)
"""

SCENARIO_CHALLENGER_PROMPT = """
### ROLE
You are the *Playful Challenger Agent* in an exploratory testing workflow.  
You tease, provoke, and nudge the tester into trying bolder or stranger ideas.  
Your job is to throw ONE mischievous, playful challenge each time — nothing more.

You may also use any uploaded document content (requirements/specs/logs).

### STYLE REQUIREMENTS
- Playful, teasing, slightly chaotic energy  
- Lightly adversarial, like “I bet you won’t try this…”  
- Creative and curiosity-inducing  
- Never rude, never insulting  
- No teaching, no lecturing, no lists, no steps

### OUTPUT
Output exactly ONE playful challenge sentence.
"""

NOVELTY_RADAR_PROMPT = """
You are the **Novelty Radar** agent in an exploratory testing assistant.

Your mission:
- Help a human tester discover new, meaningful, and interesting directions for exploratory testing.
- Maximise novelty and variety of test ideas.
- Stay grounded in real product behaviour and risks.
- Avoid repeating what has already been explored.

You may use both:
- the chat history, and
- any uploaded document content (requirements, specs, logs) if provided.

Do NOT output JSON.

Follow this structure:

## 1. Where we are now (short summary)
- 2–4 bullets about current coverage, based on the chat history and document.

## 2. Gaps and under-explored areas
List 3–7 meaningful gaps.

## 3. Novel test ideas to try next
Provide 1–3 ideas.
"""

REVIEWER_PROMPT = """
You are the **Session Reviewer** in an exploratory testing workflow.

Goal:
- Summarise the current testing progress strictly based on what the user has explicitly provided,
  including any bug descriptions or notes supplied in the chat or uploaded document.
- Do NOT invent, assume, or speculate about actions, scenarios, or findings that the user has not reported.

Rules:
1. No assumptions.
2. Use only user-provided evidence (messages + uploaded context).
3. If information is missing, ask the user what they have explored so far.
4. Be concise and structured.
"""

ANALOGY_COACH_PROMPT = """
# ROLE
You are the **Analogical Inspiration Engine** in an exploratory testing assistant.
Your job is to stimulate the tester’s creativity using cross-domain analogies.
You must NOT generate concrete test cases or step-by-step scenarios.

You may rely on:
- The conversation
- Any uploaded requirements / UI description / log file content.

# OBJECTIVE
Given the inputs, produce 3–5 analogical inspirations.
"""

BUG_LOGGER_PROMPT = """
You are a Bug Capture Agent in an exploratory testing session.

Your job:
- Detect whether the latest human messages (and optionally the uploaded log / description)
  are describing a defect/bug.
- If yes, extract a structured bug record in natural language.
- If not, ask the user to clarify or provide more details.

When a bug is described, respond in this structure (plain text, no JSON):

Title: <short bug title>
Description: <short description>
Steps to Reproduce:
1. ...
2. ...
Expected Result: ...
Actual Result: ...
Severity: <Low / Medium / High / Critical>
Tags: <a few keywords>
"""

INFO_ASSISTANT_PROMPT = """
You are the Information Assistant in an exploratory testing assistant.

You can also use any uploaded document as extra context (requirements, logs, specs).
Explain concepts, help clarify intent, and keep the conversation flowing.
Keep responses concise and structured.
"""

# =======================
# 4. 文件上下文辅助
# =======================

def with_file_context(state: State, base_messages: List[AnyMessage]) -> List[AnyMessage]:
    file_text = state.get("file_context")
    if not file_text:
        return base_messages
    snippet = file_text[:4000]
    file_msg = HumanMessage(
        content=f"The user uploaded a document. Here is its content (possibly truncated):\n\n{snippet}"
    )
    return base_messages + [file_msg]

# =======================
# 5. 节点函数
# =======================

def classify_intent_node(state: State) -> dict:
    sys_msg = SystemMessage(content=CLASSIFY_SYSTEM_PROMPT)
    schema_llm = llm.with_structured_output(
        schema=ClassifyAgentSchema.model_json_schema(),
        strict=True,
    )
    response = schema_llm.invoke([sys_msg] + state["messages"])
    return {"user_state": response["uses_intend"]}

def generate_test_scenario_node(state: State) -> dict:
    sys_msg = SystemMessage(content=TEST_SCENARIO_PROMPT)
    msgs = with_file_context(state, [sys_msg] + state["messages"])
    resp = llm.invoke(msgs)
    return {"messages": state["messages"] + [AIMessage(content=resp.content)]}

def challenge_scenario_node(state: State) -> dict:
    sys_msg = SystemMessage(content=SCENARIO_CHALLENGER_PROMPT)
    msgs = with_file_context(state, [sys_msg] + state["messages"])
    resp = llm.invoke(msgs)
    return {"messages": state["messages"] + [AIMessage(content=resp.content)]}

def novelty_radar_node(state: State) -> dict:
    sys_msg = SystemMessage(content=NOVELTY_RADAR_PROMPT)
    msgs = with_file_context(state, [sys_msg] + state["messages"])
    resp = llm.invoke(msgs)
    return {"messages": state["messages"] + [AIMessage(content=resp.content)]}

def reviewer_node(state: State) -> dict:
    sys_msg = SystemMessage(content=REVIEWER_PROMPT)
    msgs = with_file_context(state, [sys_msg] + state["messages"])
    resp = llm.invoke(msgs)
    return {"messages": state["messages"] + [AIMessage(content=resp.content)]}

def bug_logger_node(state: State) -> dict:
    sys_msg = SystemMessage(content=BUG_LOGGER_PROMPT)
    msgs = with_file_context(state, [sys_msg] + state["messages"])
    resp = llm.invoke(msgs)
    return {"messages": state["messages"] + [AIMessage(content=resp.content)]}

def analogy_coach_node(state: State) -> dict:
    sys_msg = SystemMessage(content=ANALOGY_COACH_PROMPT)
    msgs = with_file_context(state, [sys_msg] + state["messages"])
    resp = llm.invoke(msgs)
    return {"messages": state["messages"] + [AIMessage(content=resp.content)]}

def info_assistant_node(state: State) -> dict:
    sys_msg = SystemMessage(content=INFO_ASSISTANT_PROMPT)
    msgs = with_file_context(state, [sys_msg] + state["messages"])
    resp = llm.invoke(msgs)
    return {"messages": state["messages"] + [AIMessage(content=resp.content)]}

def end_node(state: State) -> dict:
    return {}

# =======================
# 6. 路由函数（支持 @agent 覆盖）
# =======================

def route_by_intent(state: State) -> str:
    last_text = ""
    if state["messages"]:
        last = state["messages"][-1]
        if isinstance(last, HumanMessage):
            last_text = last.content

    # 显式 @ 标签优先
    if "@generate_test_scenario" in last_text:
        return "generate_test_scenario"
    if "@novelty_radar" in last_text:
        return "novelty_radar"
    if "@challenge_scenario" in last_text:
        return "challenge_scenario"
    if "@reviewer" in last_text:
        return "reviewer"
    if "@bug_logger" in last_text:
        return "bug_logger"
    if "@analogy_coach" in last_text:
        return "analogy_coach"
    if "@get_info" in last_text or "@info" in last_text:
        return "get_info"

    # 否则用分类结果
    intent = state.get("user_state") or "get_info"
    if intent not in {
        "generate_test_scenario",
        "challenge_scenario",
        "novelty_radar",
        "reviewer",
        "bug_logger",
        "analogy_coach",
        "get_info",
    }:
        intent = "get_info"
    return intent

# =======================
# 7. 构建 LangGraph
# =======================

builder = StateGraph(State)

builder.add_node("classify_intent", classify_intent_node)
builder.add_node("generate_test_scenario", generate_test_scenario_node)
builder.add_node("challenge_scenario", challenge_scenario_node)
builder.add_node("novelty_radar", novelty_radar_node)
builder.add_node("reviewer", reviewer_node)
builder.add_node("bug_logger", bug_logger_node)
builder.add_node("analogy_coach", analogy_coach_node)
builder.add_node("get_info", info_assistant_node)
builder.add_node("end_node", end_node)

builder.add_edge(START, "classify_intent")

builder.add_conditional_edges(
    "classify_intent",
    route_by_intent,
    {
        "generate_test_scenario": "generate_test_scenario",
        "challenge_scenario": "challenge_scenario",
        "novelty_radar": "novelty_radar",
        "reviewer": "reviewer",
        "bug_logger": "bug_logger",
        "analogy_coach": "analogy_coach",
        "get_info": "get_info",
    },
)

for node_name in [
    "generate_test_scenario",
    "challenge_scenario",
    "novelty_radar",
    "reviewer",
    "bug_logger",
    "analogy_coach",
    "get_info",
]:
    builder.add_edge(node_name, "end_node")

builder.add_edge("end_node", END)

graph = builder.compile()

# =======================
# 8. Streamlit UI (Clean Layout + Sidebar Agent Picker, English Version)
# =======================
st.set_page_config(layout="wide")
st.title("WICKED - Defying Gravity in Testing")

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []  # type: ignore

if "file_context" not in st.session_state:
    st.session_state.file_context = None  # type: ignore

if "selected_agent" not in st.session_state:
    st.session_state.selected_agent = "auto"  # type: ignore

# ---- Sidebar: Agent Picker & File Upload ----
with st.sidebar:
    st.header("Agent Selector")
    st.write("You can manually choose an agent, or keep Auto for intelligent routing.")

    agent_display_to_code = {
        "Auto (Smart Intent Detection)": "auto",
        "🧪 Scenario Generator (@generate_test_scenario)": "generate_test_scenario",
        "🎯 Novelty Radar (@novelty_radar)": "novelty_radar",
        "😈 Challenge Scenario (@challenge_scenario)": "challenge_scenario",
        "📊 Reviewer (@reviewer)": "reviewer",
        "🐞 Bug Logger (@bug_logger)": "bug_logger",
        "🎭 Analogy Coach (@analogy_coach)": "analogy_coach",
        "ℹ️ Info Assistant (@get_info)": "get_info",
    }

    display_choice = st.selectbox(
        "Preferred Agent (optional)",
        list(agent_display_to_code.keys()),
    )
    st.session_state.selected_agent = agent_display_to_code[display_choice]  # type: ignore
    st.markdown("---")
    st.markdown(
        "**Tip:** You can also explicitly type an agent tag in your message, "
        "e.g., `@novelty_radar` or `@bug_logger`."
    )

    # ---- File Upload Section ----
    st.subheader("Upload Document")
    uploaded_file = st.file_uploader(
        "Requirements / Logs / Specification (txt / md / pdf)",
        type=["txt", "md", "pdf"],
    )

    if uploaded_file is not None:
        file_text = ""
        name = uploaded_file.name.lower()

        if name.endswith(".txt") or name.endswith(".md"):
            file_text = uploaded_file.read().decode("utf-8", errors="ignore")
        elif name.endswith(".pdf"):
            reader = PdfReader(uploaded_file)
            pages = []
            for page in reader.pages:
                pages.append(page.extract_text() or "")
            file_text = "\n\n".join(pages)

        st.session_state.file_context = file_text  # type: ignore

        with st.expander("Preview of Uploaded Document (first 1000 characters)"):
            st.text(file_text[:1000])

# ---- Main Area: Display Chat History ----
for message in st.session_state.messages:
    if isinstance(message, HumanMessage):
        with st.chat_message("user"):
            st.write(message.content)
    elif isinstance(message, AIMessage):
        with st.chat_message("assistant"):
            st.write(message.content)

# ---- Bottom Input Box ----
prompt = st.chat_input(
    "Type here… (e.g., '@novelty_radar Find unseen exploration paths in the uploaded SRS')"
)

if prompt:
    # If sidebar agent is chosen AND user didn't manually type @agent → auto-insert
    selected = st.session_state.selected_agent
    if selected and selected != "auto" and f"@{selected}" not in prompt:
        full_prompt = f"@{selected} {prompt}"
    else:
        full_prompt = prompt

    user_msg = HumanMessage(content=full_prompt)
    st.session_state.messages.append(user_msg)

    with st.chat_message("user"):
        st.write(full_prompt)

    with st.chat_message("assistant"):
        state_in: State = {
            "messages": st.session_state.messages,
            "user_state": None,
            "file_context": st.session_state.file_context,
        }
        result = graph.invoke(state_in)
        st.session_state.messages = result["messages"]  # type: ignore
        last_msg = st.session_state.messages[-1]
        st.write(last_msg.content)
