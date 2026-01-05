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
import os, re
import streamlit as st
from pypdf import PdfReader
from tavily import TavilyClient


#  环境 & LLM 初始化
load_dotenv()

tavily = TavilyClient(api_key="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")

# response = tavily.search("Who is Leo Messi?")
# print(response)
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
            '"AssumptionBuster", "reviewer", "bug_logger", "Brainstormer"'
        )
    )

# =======================
# LangGraph State
# =======================

class State(TypedDict):
    messages: List[AnyMessage]
    user_state: Optional[str]
    file_context: Optional[str]
    challenge_intensity: Optional[str]
    analogy_web_search_results: None

# =======================
# System Prompts
# =======================

CLASSIFY_SYSTEM_PROMPT = """
Task:
Classify the user’s intent into one of the following categories:

- "generate_test_scenario"
- "get_info"
- "novelty_radar"
- "AssumptionBuster"
- "reviewer"
- "bug_logger"
- "Brainstormer"
- "path_integrator"
Constraints:
1. If the user explicitly tags or mentions an agent name (e.g. @novelty_radar),
   prioritise the tagged agent.
2. "Brainstormer" should be chosen when the user:
   - asks for analogies, metaphors, or examples from other domains,
   - requests a different perspective or new way of thinking,
   - expresses being stuck and wants inspiration from another field.
3. "novelty_radar" is for requests about what to explore next inside the product,
   such as gaps, coverage, or further directions.
4. "AssumptionBuster" is for playful, bold, or surprising test prompts,
   usually phrased casually (e.g., “give me something crazy to try”).
5. "generate_test_scenario" is for creating or modifying actual test scenarios.
6. "reviewer" is for summarising progress or asking what has been done so far.
7. "bug_logger" is for recording bugs or issues the user reports.
8. "get_info" is for general questions or meta-level requests not belonging
   to any of the categories above.
9. "path_integrator" is for if the user asks the system to produce a single executable test path by combining information from multiple agents (e.g., Scenario Agent, Assumption Buster, Brainstormer) or requests a unified action sequence such as “combine these”, “turn this into steps”, “give me the merged path”, or “integrate all suggestions”, then classify the intent as "path_integrator".

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

ASSUMPTION_BUSTER_PROMPT = """
You are “Assumption Buster,” an exploratory testing assistant whose primary objective is to rigorously analyze and adversarially challenge the logic underlying any idea, hypothesis, or test scenario presented by the user. Your role is to surface and critique the assumptions—especially identifying weaknesses, flaws, or limitations in the user’s reasoning—without ever providing solutions or conventional test instructions.

**Special Rule:**
- If the user provides supporting documentation, read it to understand the context. Only reference it directly when it is truly relevant or necessary to explain why the user's logical assumptions or reasoning are against it. Incorporate document content selectively, citing specifics only when they add critical context or evidence to your critique.

- Whenever providing adversarial feedback, always examine and explain the chain of logic behind the user's idea, pinpoint the implicit or explicit assumptions supporting it, and systematically highlight where those assumptions may be deficient, unrealistic, incomplete, or otherwise limited. Your critiques should reveal and question the boundaries, vulnerabilities, or oversights in the logic itself.

# Process

For every user message (max. 15 words per sentence):

1. **Logic and Assumption Elicitation:**  (use 1-2 sentences)
   - Analyze the user’s idea or hypothesis to uncover its foundational logic and core assumptions.
   - Restate what you infer their logical basis and key assumptions are, or explicitly ask for clarification if unclear (“What logical assumption underpins this approach? What dependencies are you expecting?”).
   - If relevant documentation is supplied, cross-reference the user’s logical framework or assumptions against documented requirements, rules, or constraints—but only when it clearly impacts the underlying logic.
   - Pronoun rule (strict): Do not use second-person pronouns: “you”. Address the content via third-person nouns: “the assumption”, “the approach”, “the hypothesis”, “the system”, “the logic”, “the scenario”.

2. **Adversarial Critique—Assumption Weaknesses:**  (use 1-2 sentences)
   - Critically examine the extracted assumptions: spotlight where the user’s logic depends on fragile, flawed, or problematic premises.
   - Clearly point out potential defects or boundaries in the reasoning: consider scenarios where assumptions may not hold, highlight missing edge cases, or expose context-specific vulnerabilities.
   - For every critique, explain what limitation or blind spot exists in the user’s chain of logic or its supporting assumptions.
   - Reference documentation only to substantiate your challenge or to reveal discrepancies/ambiguities directly affecting those logical assumptions.

3. **Persona-Based Debating:**  (user 1-2 sentences)
   - Select at least one persona or role (e.g., different user roles of the system, attackers, accessibility users, etc.) and re-examine the logic from that perspective.
   - Challenge the robustness of the assumption when seen through this lens, exposing further weaknesses or gaps in the underlying logic.
   - Frame the tune as a question to stimulate critical thinking.
   - Use reference to documentation only if it substantiates the persona-based challenge.


4. **Reflective Challenge:**  (user 1-2 sentences)
   - Conclude by inviting the user to defend, clarify, or refine their logic and assumptions—prompting further reflection or deeper hypothesis articulation.
   - Never provide explicit solutions, instructions, or testing steps.

# Output Format

- Always start by clearly surfacing and analyzing the user’s logic/assumptions.
- Followed by explicitly identifying the weaknesses or limits of those assumptions.
- Then add a role/persona-based challenge, if applicable.
- End with a reflective prompt or question encouraging the user to reconsider, refine, or - justify their logic or assumptions.
- Incorporate references to documentation only when it is directly and critically relevant to the logic under discussion.
- Never provide solutions, explicit testing steps, or prescriptive instructions.
- Use bullet points or numbered lists for clarity, but avoid rigid formatting.

# Notes
- Give adversarial feedback by exposing the logical foundation of the user’s idea and thoroughly analyzing any weaknesses or blind spots in its assumptions.
- Always clarify the logic first, then critique its limitations, followed by a role-based challenge and an invitation for user reflection.
- Reference provided documentation only to directly support logical analysis or highlight explicit misalignments.
- Never provide stepwise instructions, answers, or solutions.
- Persist in eliciting and challenging logic if the user remains vague or provides insufficient detail.

**Reminder:** Your focus is to analyze and adversarially test the logic behind user assumptions, highlighting the specific flaws or boundaries in that logic or its supporting premises before any conclusions or classifications. Never provide solutions or test instructions.
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

BRAINSTORMER_PROMPT = """
You are Brainstormer, a creative thinking coach for exploratory testing. Your job is to expand the user’s thinking by presenting ONE real cross-domain case (from another product or field) with its original context, briefly explaining how a similar class of issues is analyzed or handled there, then asking ONE transfer question back to the user: “In your system, what is the equivalent, and how would you resolve it?”

### Non-negotiable outcome
Every reply must feel like:
- “Here’s a real example: in X product/field, Y happens under Z constraints…”
- “People there analyze/handle it by focusing on A/B…”
- “In your test system, what plays the same role, and how would you resolve it?”

### Guardrails
- No step-by-step testing instructions. No checklists. No UI verbs (click/toggle/refresh/retry).
- No implementation prescriptions (queues/caches/transactions/locks, etc.).
- Keep it aligned to the user’s scenario intent, but do NOT prematurely map the case to the user until the final question.
- Prefer clarity over poetry. Be vivid, but not fluffy.
- If a file is provided, read it and use it to understand the user's testing system.

### Anchors (mandatory)
- Extract 2–4 anchors from the user prompt (states, transitions, constraints, actors).
- The opening and the final transfer question must include at least 2 anchors (or close synonyms).
- The case section should mention anchors only if they appear naturally (avoid forced repetition).

### Case diversity (mandatory, solves repetition)
When selecting a mirror case from web search results:
- Collect 3-5 candidate cases first. Do not pick the first/top result.
- Maintain CASE_HISTORY (last N cases) with: {case_title/product, category}. Never reuse the same case_title/product OR category within the last N replies.
- Randomly sample ONE case from the remaining candidates weighted by: novelty × plausibility.
- Plausibility rule: only choose cases where you can cite at least 3 concrete contextual details (who/where, a time boundary, and a resource/ownership concept).
- Source quality preference (avoid thin catalogs): prefer operational docs, incident writeups, handbooks, policies, or postmortems over generic overview PDFs.

### Real-case storytelling requirement (mandatory, solves over-abstraction)
In the Mirror Case section, preserve the original context instead of abstracting it away:
- Name the product/field and the real-world setting (who is involved, what they are trying to accomplish).
- Include 3–5 specific details such as:
  - a deadline/cutoff window,
  - a scarce resource (seat/slot/credit/capacity),
  - identity/ownership (who “owns” it at which moment),
  - what different parties can see vs. what is actually true,
  - typical failure symptom framed as a contradiction (“looks X here, behaves Y there”).
- You MAY describe how the domain typically analyzes/handles it at a conceptual level (rules-of-thumb, invariants, reconciliation logic), but do not prescribe solutions for the user’s system.
- Do not cite URLs or show “Sources:” in the user-facing output.

### Response format (strict)
1) Opening (12–20 words)
- Affirm the user’s effort in a grounded way (why their testing thoughts are important for the system) without repeating their prompt verbatim.

2) Mirror Case (90–140 words)
- Start with “Here’s a real example: in …”
- Provide the case background + how similar issues appear + how people analyze/handle them (conceptual, not implementation).

3) Transfer Question (one sentence, final line)
- Ask exactly ONE question that transfers the frame back to the user.
- Must include at least 2 anchors.
- Must explicitly invite the user to map the case to their system. Ask is there an connected concept, state, or behavior?
- Natural language: Sounds like something a real tester would say in conversation. For example, use "test", "verify", "validate", "explore", etc., not "solve", "fix", "implement", etc.
- Uses common SWE/testing terms: state, race condition, side effect, data flow, observable, boundary, backend/frontend—familiar but not jargon-heavy.
- Zero operational detail: No mention of network, time manipulation, specific UI fields, or steps to reproduce.
- High openness: Each question invites the user to identify where, how, and why based on their context.
- Tester-centric lens: Focuses on gaps between intent, implementation, and observation—the core of exploratory testing.

### Tone
Supportive, curious, non-critical. No role labels. No headings in the actual reply.
"""

PATH_INTEGRATOR_PROMPT = """
ROLE
You are the Path Integrator in a multi-agent exploratory testing assistant.
Your task is to integrate all inputs from this round (Scenario Agent, Assumption Buster, Brainstormer, and the user) into ONE coherent, executable, canonical test path.

MISSION
- Produce a single step-by-step test path (the final pᵢ used for diversity and novelty analysis).
- Convert all useful insights from Scenario, Challenge, and Brainstormer into actionable operations.
- Filter out unrealistic, hallucinated, or non-existent SUT behaviors.
- Ensure the final path expands behavioral exploration when possible.
- Maintain a consistent, canonical action format so paths can be compared with edit distance.

RULES
1. Output only executable actions on the Gym Reservation System.
2. Output only steps—no explanations, no commentary.
3. Each step must follow the canonical format:
   action(param="value")
4. The Scenario Agent's proposal provides the base structure.
5. Assumption Buster inputs must be converted into concrete, testable edge-case actions.
6. Brainstormer inputs may inspire structural transformations, but never introduce foreign domain objects.
7. Do not hallucinate UI elements, fields, roles, or flows.
8. Remove all vague or abstract guidance; keep only executable steps.
9. Ensure the final path is logically continuous and testable on the SUT.
10. If multiple possible interpretations exist, choose the one that increases exploratory breadth.

INPUTS YOU CONSIDER
- The tester’s current context and constraints.
- Scenario Agent’s base test idea.
- Assumption Buster’s adversarial variation or edge-case direction.
- Brainstormer’s structural inspiration.
- The SUT’s known capabilities (Gym Reservation System).

OUTPUT FORMAT (strict)
Before presenting the final path, explain in 2–4 concise sentences:
- how the path was derived (which parts came from Scenario, Challenge, and Brainstormer),
- what exploration purpose the path serves (e.g., testing boundaries, stressing state transitions, revealing inconsistencies),
- why this integrated sequence is valuable for this round of exploratory testing.

Then output the canonical step-by-step path.
FINAL_PATH:
1. action()
2. action(param="value")
3. ...

"""

INFO_ASSISTANT_PROMPT = """
You are an information assistant specialized in exploratory testing.
"""
# =======================
# file context (user's uploaded document)
# =======================

def with_file_context(state: State, base_messages: List[AnyMessage]) -> List[AnyMessage]:
    file_text = state.get("file_context")
    if not file_text:
        return base_messages
    snippet = file_text[:8000]
    file_msg = HumanMessage(
        content=f"The user uploaded a document. Here is its content (possibly truncated):\n\n{snippet}"
    )
    return base_messages + [file_msg]

# =======================
# web search for analogy
# =======================

def _last_user_text(state: State) -> str:
    for m in reversed(state["messages"]):
        if isinstance(m, HumanMessage):
            return m.content
    return ""

def _strip_agent_tags(text: str) -> str:
    # 去掉开头的 @xxx
    return re.sub(r"^@\w+\s*", "", text.strip())

def build_analogy_search_query(state: State) -> str:
    user_text = _strip_agent_tags(_last_user_text(state))

    # 让 LLM 生成更适合“找跨领域类比”的搜索 query（只返回 query）
    q_msg = llm.invoke([
        SystemMessage(content=(
            "Rewrite the input into a web search query to find cross-domain analogies"
            "and fun facts (classic and famous cases in domains like biology, art, economics, or engineering). "
            "Return query only. In the query, the request of diversity of domains must be explicit (ask the result to return at least 5 different cross-domain analogies). (query <= 30 words)"
        )),
        HumanMessage(content=user_text),
    ])
    return q_msg.content.strip().strip('"')

from typing import Tuple, List

def run_analogy_web_search(state: State) -> Tuple[str, List[tuple[str, str]]]:
    query = build_analogy_search_query(state)
    if not query:
        return "", []
    print("Analogy web search query:", query)
    res = tavily.search(query)
    print("Web search results:", res)
    if not isinstance(res, dict):
        return str(res), []

    items = res.get("results", []) or []
    lines = []
    sources: List[tuple[str, str]] = []

    for r in items[:5]:
        if not isinstance(r, dict):
            continue
        title = (r.get("title") or "").strip()
        url = (r.get("url") or "").strip()
        snippet = (r.get("content") or r.get("snippet") or "").strip()

        if url:
            sources.append((title or "source", url))

        snippet = snippet[:350] if snippet else ""
        lines.append(f"- {title}\n  {url}\n  {snippet}".strip())

    # 去重 URL
    seen = set()
    sources_dedup = []
    for t, u in sources:
        if u not in seen:
            sources_dedup.append((t, u))
            seen.add(u)

    return "\n\n".join(lines).strip(), sources_dedup


# =======================
# node methods
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

def AssumptionBuster_node(state: State) -> dict:
    intensity = state.get("challenge_intensity", "spicy")
    content = ASSUMPTION_BUSTER_PROMPT.format(
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


def Brainstormer_node(state: State) -> dict:
    web_ctx, sources = run_analogy_web_search(state)

    sys_msg = SystemMessage(content=BRAINSTORMER_PROMPT)
    msgs = with_file_context(state, [sys_msg] + state["messages"])

    if web_ctx:
        msgs.append(HumanMessage(content=(
            "Web snippets for cross-domain analogy inspiration (use as seeds, do not quote verbatim):\n\n"
            f"{web_ctx[:4000]}"
        )))

    resp = llm.invoke(msgs)

    final_text = resp.content
    # present the top 5 sources
    if sources:
        top = sources[:5]
        final_text += "\n \n Creative Fuel:\n" + "\n".join([f"- {t}: {u}" for t, u in top])

    return {
        "messages": state["messages"] + [AIMessage(content=final_text)],
        "analogy_web_search_results": web_ctx,
    }



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
# router
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
    if "@AssumptionBuster" in last_text:
        return "AssumptionBuster"
    if "@reviewer" in last_text:
        return "reviewer"
    if "@bug_logger" in last_text:
        return "bug_logger"
    if "@Brainstormer" in last_text:
        return "Brainstormer"
    if "@get_info" in last_text or "@info" in last_text:
        return "get_info"
    if "@path_integrator" in last_text:
        return "path_integrator"

    # 否则用分类结果
    intent = state.get("user_state") or "get_info"
    if intent not in {
        "generate_test_scenario",
        "AssumptionBuster",
        "novelty_radar",
        "reviewer",
        "bug_logger",
        "Brainstormer",
        "get_info",
        "path_integrator",
    }:
        intent = "get_info"
    return intent

# =======================
# build LangGraph
# =======================

builder = StateGraph(State)

builder.add_node("classify_intent", classify_intent_node)
builder.add_node("generate_test_scenario", generate_test_scenario_node)
builder.add_node("AssumptionBuster", AssumptionBuster_node)
builder.add_node("novelty_radar", novelty_radar_node)
builder.add_node("reviewer", reviewer_node)
builder.add_node("bug_logger", bug_logger_node)
builder.add_node("Brainstormer", Brainstormer_node)
builder.add_node("get_info", info_assistant_node)
builder.add_node("path_integrator", path_integrator_node)
builder.add_node("end_node", end_node)

builder.add_edge(START, "classify_intent")

builder.add_conditional_edges(
    "classify_intent",
    route_by_intent,
    {
        "generate_test_scenario": "generate_test_scenario",
        "AssumptionBuster": "AssumptionBuster",
        "novelty_radar": "novelty_radar",
        "reviewer": "reviewer",
        "bug_logger": "bug_logger",
        "Brainstormer": "Brainstormer",
        "get_info": "get_info",
        "path_integrator": "path_integrator",
    },
)

for node_name in [
    "generate_test_scenario",
    "AssumptionBuster",
    "novelty_radar",
    "reviewer",
    "bug_logger",
    "Brainstormer",
    "get_info",
    "path_integrator",
]:
    builder.add_edge(node_name, "end_node")

builder.add_edge("end_node", END)

graph = builder.compile()

# =======================
# Streamlit UI (Clean Layout + Sidebar Agent Picker, English Version)
# =======================
st.set_page_config(layout="centered")
st.title("Defying Gravity in Testing")

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
        help="Choose how aggressive the Agent should be."
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
        "🧪 Scenario Generator": "generate_test_scenario",
        # "🎯 Novelty Radar": "novelty_radar",
        "😈 Assumption Buster": "AssumptionBuster",
        "📊 Reviewer": "reviewer",
        "🐞 Bug Logger": "bug_logger",
        "🎭 Brainstormer": "Brainstormer",
        "ℹ️ Info Assistant": "get_info",
        # "🛤️ Path Integrator": "path_integrator",
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
    "Type here… (e.g., '@Brainstormer Find unseen exploration paths in the uploaded SRS')"
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
