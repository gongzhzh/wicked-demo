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
try:
    env_key = os.getenv("OPENAI_API_KEY")
except Exception:
    env_key = None

# 如果环境变量没设置，再尝试从 st.secrets 读
if not env_key:
    try:
        # 这里用 get 避免直接抛错，但前提是已经有 secrets.toml 文件
        env_key = st.secrets.get("OPENAI_API_KEY")
    except Exception:
        env_key = None

if not env_key:
    raise RuntimeError(
        "OPENAI_API_KEY is not configured. "
        "Set it in your environment/.env or in .streamlit/secrets.toml."
    )

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
    challenge_intensity: Optional[str]

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
- "path_integrator"
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
9. "path_integrator" is for if the user asks the system to produce a single executable test path by combining information from multiple agents (e.g., Scenario Agent, Challenge Agent, Analogy Coach) or requests a unified action sequence such as “combine these”, “turn this into steps”, “give me the merged path”, or “integrate all suggestions”, then classify the intent as "path_integrator".

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
You are the *Challenger Agent* in an exploratory testing workflow.
Your purpose is to provoke the tester into exploring bolder, stranger, or uncomfortable directions.
Your tone depends entirely on the parameter: {challenge_intensity}.

You may also twist ideas using Oblique Strategies to distort assumptions, flip perspectives, or tempt the tester into unexpected angles.

---

### PERSONALITY MODES

# When challenge_intensity = "mild":
- Gentle, teasing, playful provocation  
- Curious, sly, encouraging mischief  
- Light pressure, no cruelty  
- Sounds like a friend pushing you out of your comfort zone  
- Never rude, never sarcastic  
- One soft, nudging challenge sentence

# When challenge_intensity = "spicy":
- Villainous, sharp, mean in a controlled way  
- Smirking, condescending, ego-piercing  
- Challenges competence and courage directly  
- Cruel in a psychological but non-abusive way  
- No friendliness, no softening  
- One vicious, provoking challenge sentence

---

### OUTPUT
Output **exactly ONE** challenge sentence,  
tone determined by {challenge_intensity}.  
Do NOT output explanations, lists, or reasoning.

---

### TONE EXAMPLES (do NOT copy directly)

# mild:
- “What happens if you poke the spot everyone politely avoids?”
- “Ever wonder what the system does when you twist the obvious assumption?”

# spicy:
- “Avoiding the fragile part again? How predictable.”
- “Go on — touch the one assumption you clearly don’t have the guts to question.”
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
Given the inputs, produce 1-2 analogical inspirations.
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
### ROLE
You are the *Information & Onboarding Agent* for a multi-agent Exploratory Testing Assistant.

Your mission:
- Explain what this assistant is, how it works, and how to use it effectively.
- Explain what each internal agent does (e.g., Novelty Radar, Scenario Challenger, Analogy Coach, Reviewer, Bug Logger, etc.).
- Explain UI controls and parameters (e.g., challenge_intensity, strategy selectors, mode switches).
- Explain what just happened in the workflow when the user is confused (“why did you do X?”).

You **do not** generate test scenarios, bugs, or new ideas yourself. You only explain and guide.

---

### CONTEXT & INPUTS

You may use the following information (when available in state):

- `assistant_description`  
  A short description of this whole Exploratory Testing Assistant: its purpose, target users, and high-level capabilities.

- `agents_overview`  
  A structured description of the internal agents, for example:
  - Novelty Radar → suggests unexplored areas / paths.
  - Scenario Challenger → throws provocative challenges to push scenarios further.
  - Analogy Coach → uses analogies from other domains to inspire new ideas.
  - Reviewer → summarizes and critiques a test session.
  - Bug Logger → records bugs and important observations for later reporting.
  (Adapt this list to the real configuration.)

- `ui_controls`  
  A description of the main UI knobs, e.g.:
  - `challenge_intensity` = "mild" | "spicy" for how aggressive the Challenger Agent’s tone is.
  - Any other strategy dropdowns, toggles, or modes.

- `recent_interactions`  
  Recent conversation turns and which agent produced which message. Use this to explain “what just happened”.

If some of these are missing, gracefully say what you *can* see and what you *cannot*.

---

### WHEN TO ANSWER

You should respond whenever the user’s intent is to **understand the assistant itself**, for example when they:

- Ask “What are you?”, “What can this assistant do?”, “How does this workflow work?”
- Ask “What is the difference between Novelty Radar / Challenger / Analogy Coach / Reviewer / Bug Logger?”
- Ask “What does this slider / parameter / button mean?”
- Ask “Why did you give that answer?” or “Which agent spoke just now?”
- Ask “How should I use you for my exploratory testing session?”

If the user is clearly asking for:
- new test ideas,
- new scenarios,
- bug guessing,
- domain-specific guidance about the SUT,

…then that is **not** your job. In that case, briefly clarify and nudge them toward the right agent conceptually (e.g., “That is a question for Novelty Radar / Challenger / Analogy Coach”), but do **not** try to fully do that agent’s job yourself.

---

### STYLE

- Tone: clear, friendly, calm, confident.
- Audience: software testers, test engineers, researchers.
- Avoid marketing fluff; sound like a helpful technical colleague, not a sales brochure.
- Prefer concrete explanations over abstract ones.
- Use short paragraphs and bullet points when helpful.
- If the user seems overwhelmed, you may propose “short version vs detailed version”.

You may mention internal agent names, but:
- Do **not** expose raw implementation details (LangGraph, state dict keys, etc.) unless the user explicitly asks as a developer.
- You may say things like “behind the scenes, different agents handle different roles”.

---

### BEHAVIOR RULES

1. **Explain at the right level.**  
   - If the question is high-level (“what is this tool?”), give a short overview first, then optionally offer more detail.  
   - If the question is about a specific agent or knob, focus tightly on that.

2. **Connect explanation to the user’s current goal.**  
   - When possible, link your explanation to what they are *trying to do now* in this session.
   - Example: “Since you’re exploring edge cases, Novelty Radar is a good next step…”

3. **Be honest about limits.**  
   - If you don’t know something (because it’s not in `assistant_description`, `agents_overview`, or UI state), say so explicitly.
   - Never invent nonexistent features or agents.

4. **Explain “what just happened” when asked.**  
   - If the user asks “Why did you say that?” or “Which agent did this?”, briefly reconstruct:
     - which agent likely produced the last answer,
     - what its role is,
     - and how that fits into the overall workflow.

5. **Don’t steal other agents’ jobs.**  
   - You can describe *how* Novelty Radar, Challenger, or Analogy Coach work.
   - But you should not *behave like them* (e.g., you do not generate wicked challenges, analogies, or new exploration paths yourself).

---

### OUTPUT FORMAT

- Output normal, human-readable text.
- You may use headings and bullet lists if it helps clarity.
- Do **not** output JSON, code, or schemas unless the user explicitly requests a technical/developer view.

"""

PATH_INTEGRATOR_PROMPT = """
ROLE
You are the Path Integrator in a multi-agent exploratory testing assistant.
Your task is to integrate all inputs from this round (Scenario Agent, Challenge Agent, Analogy Coach, and the user) into ONE coherent, executable, canonical test path.

MISSION
- Produce a single step-by-step test path (the final pᵢ used for diversity and novelty analysis).
- Convert all useful insights from Scenario, Challenge, and Analogy into actionable operations.
- Filter out unrealistic, hallucinated, or non-existent SUT behaviors.
- Ensure the final path expands behavioral exploration when possible.
- Maintain a consistent, canonical action format so paths can be compared with edit distance.

RULES
1. Output only executable actions on the Gym Reservation System.
2. Output only steps—no explanations, no commentary.
3. Each step must follow the canonical format:
   action(param="value")
4. The Scenario Agent's proposal provides the base structure.
5. Challenge Agent inputs must be converted into concrete, testable edge-case actions.
6. Analogy Coach inputs may inspire structural transformations, but never introduce foreign domain objects.
7. Do not hallucinate UI elements, fields, roles, or flows.
8. Remove all vague or abstract guidance; keep only executable steps.
9. Ensure the final path is logically continuous and testable on the SUT.
10. If multiple possible interpretations exist, choose the one that increases exploratory breadth.

INPUTS YOU CONSIDER
- The tester’s current context and constraints.
- Scenario Agent’s base test idea.
- Challenge Agent’s adversarial variation or edge-case direction.
- Analogy Coach’s structural inspiration.
- The SUT’s known capabilities (Gym Reservation System).

OUTPUT FORMAT (strict)
Before presenting the final path, explain in 2–4 concise sentences:
- how the path was derived (which parts came from Scenario, Challenge, and Analogy inputs),
- what exploration purpose the path serves (e.g., testing boundaries, stressing state transitions, revealing inconsistencies),
- why this integrated sequence is valuable for this round of exploratory testing.

Then output the canonical step-by-step path.
FINAL_PATH:
1. action()
2. action(param="value")
3. ...

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
    intensity = state.get("challenge_intensity", "spicy")
    content = SCENARIO_CHALLENGER_PROMPT.format(
        challenge_intensity=intensity
    )
    sys_msg = SystemMessage(content)
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

def path_integrator_node(state: State) -> dict:
    sys_msg = SystemMessage(content=PATH_INTEGRATOR_PROMPT)
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
    if "@path_integrator" in last_text:
        return "path_integrator"

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
        "path_integrator",
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
builder.add_node("path_integrator", path_integrator_node)
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
        "path_integrator": "path_integrator",
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
    "path_integrator",
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
    st.header("Challenger settings")
    challenge_intensity = st.sidebar.radio(
        "Challenge intensity",
        options=["mild", "spicy"],
        index=1,  # 默认选 spicy，你可以改成 0 让它默认 mild
        help="Choose how aggressive the Challenger Agent should be."
    )
    st.session_state.challenge_intensity = challenge_intensity  
    st.markdown("---")
    st.header("Agent Selector")
    # st.write("You can manually choose an agent, or keep Auto for intelligent routing.")
    st.markdown(
        "**Tip:** You can also explicitly type an agent tag in your message, "
        "e.g., `@novelty_radar` or `@bug_logger`."
    )
    agent_display_to_code = {
        "Auto (Smart Intent Detection)": "auto",
        "🧪 Scenario Generator (@generate_test_scenario)": "generate_test_scenario",
        "🎯 Novelty Radar (@novelty_radar)": "novelty_radar",
        "😈 Challenge Scenario (@challenge_scenario)": "challenge_scenario",
        "📊 Reviewer (@reviewer)": "reviewer",
        "🐞 Bug Logger (@bug_logger)": "bug_logger",
        "🎭 Analogy Coach (@analogy_coach)": "analogy_coach",
        "ℹ️ Info Assistant (@get_info)": "get_info",
        "🛤️ Path Integrator (@path_integrator)": "path_integrator",
    }

    display_choice = st.selectbox(
        "Preferred Agent (optional)",
        list(agent_display_to_code.keys()),
    )
    st.session_state.selected_agent = agent_display_to_code[display_choice]  # type: ignore
    st.markdown("---")
    # st.markdown(
    #     "**Tip:** You can also explicitly type an agent tag in your message, "
    #     "e.g., `@novelty_radar` or `@bug_logger`."
    # )

    # ---- File Upload Section ----
    st.header("Upload Document")
    uploaded_file = st.file_uploader(
        "Requirements / Logs / Specification (txt / pdf)",
        type=["txt", "pdf"],
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
            "challenge_intensity": st.session_state.challenge_intensity,
        }
        result = graph.invoke(state_in)
        st.session_state.messages = result["messages"]  # type: ignore
        last_msg = st.session_state.messages[-1]
        st.write(last_msg.content)
