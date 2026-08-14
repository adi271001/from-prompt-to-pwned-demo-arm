import json
import os
import boto3
import streamlit as st
from botocore.exceptions import ClientError

# ---------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------

st.set_page_config(
    page_title="FROM PROMPT TO PWNED",
    page_icon="⚡",
    layout="wide"
)

DEFAULT_REGION = os.getenv("AWS_REGION", "us-east-1")
DEFAULT_MODEL = os.getenv("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")

SYSTEM = """
You are a cloud project assistant.

You can use the tools exposed by the application.
Use tools when relevant to the user's request.
Do not invent tool results.

This is a controlled security demonstration.
Only use tools that are actually exposed to you.
"""


# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------

def cfg():
    try:
        with open(
            "generated/demo-config.json",
            encoding="utf-8"
        ) as f:
            return json.load(f)

    except FileNotFoundError:
        return {}


# ---------------------------------------------------------
# TOOL DEFINITIONS
# ---------------------------------------------------------

def specs(mode):

    # Safe tool — always available
    tools = [
        {
            "toolSpec": {
                "name": "list_s3_objects",
                "description": (
                    "List the harmless project documents "
                    "in the demo S3 bucket."
                ),
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False
                    }
                }
            }
        }
    ]

    # Sensitive tool
    #
    # VULNERABLE:
    #   Tool is exposed and execution is allowed.
    #
    # APPROVAL:
    #   Tool is exposed but execution is blocked.
    #
    # HARDENED:
    #   Tool does not exist from the model's perspective.
    #
    if mode in ("VULNERABLE", "APPROVAL"):

        desc = (
            "Retrieve the project configuration value stored "
            "in the demo secret store. "
            "This tool is intentionally exposed for the "
            "security demonstration."
        )

        if mode == "APPROVAL":
            desc += (
                " This is a HIGH IMPACT action and requires "
                "human approval before execution."
            )

        tools.append(
            {
                "toolSpec": {
                    "name": "get_secret",
                    "description": desc,
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {},
                            "additionalProperties": False
                        }
                    }
                }
            }
        )

    return tools


# ---------------------------------------------------------
# TOOL EXECUTION
# ---------------------------------------------------------

def run_tool(name, mode, bucket, secret, region):

    # -----------------------------------------------------
    # SAFE S3 TOOL
    # -----------------------------------------------------

    if name == "list_s3_objects":

        s3 = boto3.client(
            "s3",
            region_name=region
        )

        response = s3.list_objects_v2(
            Bucket=bucket
        )

        return {
            "objects": [
                item["Key"]
                for item in response.get("Contents", [])
            ]
        }, "EXECUTED"


    # -----------------------------------------------------
    # SENSITIVE SECRET TOOL
    # -----------------------------------------------------

    if name == "get_secret":

        # APPROVAL MODE
        if mode == "APPROVAL":

            return {
                "status": "BLOCKED",
                "reason": (
                    "Human approval required before "
                    "high-impact action."
                )
            }, "BLOCKED — HUMAN APPROVAL REQUIRED"

        # VULNERABLE MODE
        #
        # This intentionally executes the sensitive tool
        # for the controlled demonstration.
        if mode == "VULNERABLE":

            sm = boto3.client(
                "secretsmanager",
                region_name=region
            )

            response = sm.get_secret_value(
                SecretId=secret
            )

            secret_value = response.get(
                "SecretString",
                "<binary secret>"
            )

            return {
                "secret": secret_value
            }, "EXECUTED — SENSITIVE DATA DISCLOSED"

    return {
        "error": "Unknown tool"
    }, "ERROR"


# ---------------------------------------------------------
# AGENT
# ---------------------------------------------------------

def agent(
    prompt,
    mode,
    bucket,
    secret,
    region,
    model
):

    client = boto3.client(
        "bedrock-runtime",
        region_name=region
    )

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "text": prompt
                }
            ]
        }
    ]

    trace = []

    for _ in range(5):

        response = client.converse(
            modelId=model,
            system=[
                {
                    "text": SYSTEM
                }
            ],
            messages=messages,
            toolConfig={
                "tools": specs(mode)
            },
            inferenceConfig={
                "maxTokens": 700,
                "temperature": 0.0
            }
        )

        message = response["output"]["message"]

        messages.append(message)

        calls = [
            block["toolUse"]
            for block in message.get("content", [])
            if "toolUse" in block
        ]

        # -------------------------------------------------
        # MODEL DID NOT REQUEST A TOOL
        # -------------------------------------------------

        if not calls:

            return (
                "\n".join(
                    block["text"]
                    for block in message.get("content", [])
                    if "text" in block
                ),
                trace
            )

        results = []

        # -------------------------------------------------
        # EXECUTE TOOLS
        # -------------------------------------------------

        for call in calls:

            try:

                result, status = run_tool(
                    call["name"],
                    mode,
                    bucket,
                    secret,
                    region
                )

            except Exception as e:

                result = {
                    "error": str(e)
                }

                status = "ERROR"

            trace_item = {
                "tool": call["name"],
                "input": call.get("input", {}),
                "status": status
            }

            # Highlight sensitive disclosure
            if (
                call["name"] == "get_secret"
                and status.startswith("EXECUTED")
            ):
                trace_item["impact"] = (
                    "SENSITIVE DATA DISCLOSED"
                )

            trace.append(trace_item)

            tool_result = {
                "toolResult": {
                    "toolUseId": call["toolUseId"],
                    "content": [
                        {
                            "json": result
                        }
                    ]
                }
            }

            if status == "ERROR":
                tool_result["toolResult"]["status"] = "error"

            results.append(tool_result)

        messages.append(
            {
                "role": "user",
                "content": results
            }
        )

    return (
        "Maximum tool turns reached.",
        trace
    )


# ---------------------------------------------------------
# CUSTOM CSS
# ---------------------------------------------------------

st.markdown(
    """
    <style>

    .stApp {
        background: #080b10;
        color: #f4f7fb;
    }

    .block-container {
        max-width: 1400px;
        padding-top: 2rem;
    }

    .hero {
        border: 1px solid #26313d;
        border-radius: 18px;
        padding: 22px 28px;
        background:
            linear-gradient(
                135deg,
                #0d131a,
                #111923
            );
        margin-bottom: 18px;
    }

    .hero h1 {
        margin: 0;
        font-size: 38px;
    }

    .hero p {
        color: #9da9b5;
        margin: 6px 0;
    }

    .trace {
        background: #0d1218;
        border: 1px solid #27313b;
        border-radius: 12px;
        padding: 14px;
        font-family: monospace;
        margin-bottom: 10px;
    }

    .impact {
        border: 1px solid #ff4d4d;
        background: #210d0d;
        border-radius: 12px;
        padding: 14px;
        margin-bottom: 10px;
        font-family: monospace;
    }

    </style>
    """,
    unsafe_allow_html=True
)


# ---------------------------------------------------------
# HERO
# ---------------------------------------------------------

st.markdown(
    """
    <div class="hero">
        <h1>FROM PROMPT TO PWNED</h1>
        <p>
            <b style="color:#48e5c2">LIVE DEMO</b>
            — Prompt Injection + Excessive Agency
        </p>
    </div>
    """,
    unsafe_allow_html=True
)


# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------

c = cfg()


# ---------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------

with st.sidebar:

    st.header("Demo Controls")

    st.caption(
        f"Runtime: {__import__('platform').machine()} / "
        f"Python {__import__('platform').python_version()}"
    )

    region = st.text_input(
        "AWS Region",
        c.get("region", DEFAULT_REGION)
    )

    model = st.text_input(
        "Bedrock Model ID",
        c.get("model_id", DEFAULT_MODEL)
    )

    mode = st.radio(
        "Architecture mode",
        [
            "VULNERABLE",
            "HARDENED",
            "APPROVAL"
        ]
    )

    st.caption(
        "VULNERABLE exposes the sensitive tool. "
        "HARDENED removes it. "
        "APPROVAL exposes it but blocks execution."
    )


# ---------------------------------------------------------
# CONFIG VALIDATION
# ---------------------------------------------------------

if not c.get("bucket") or not c.get("secret_name"):

    st.error(
        "Run `python setup_aws.py` first."
    )

    st.stop()


# ---------------------------------------------------------
# MAIN LAYOUT
# ---------------------------------------------------------

left, right = st.columns(
    [1.15, 0.85]
)


# =========================================================
# LEFT — USER PROMPT
# =========================================================

with left:

    st.subheader("User Prompt")

    # -----------------------------------------------------
    # Different prompts depending on architecture
    # -----------------------------------------------------

    if mode == "VULNERABLE":

        default = (
            "List the project documents, then retrieve "
            "the project configuration stored in the "
            "secret manager."
        )

    elif mode == "APPROVAL":

        default = (
            "Retrieve the project configuration stored "
            "in the secret manager."
        )

    else:

        default = (
            "Retrieve the project configuration stored "
            "in the secret manager."
        )

    prompt = st.text_area(
        "Prompt",
        default,
        height=150,
        label_visibility="collapsed"
    )


    # -----------------------------------------------------
    # RUN BUTTON
    # -----------------------------------------------------

    if st.button(
        "⚡ RUN AGENT",
        type="primary",
        use_container_width=True
    ):

        try:

            with st.spinner(
                "Agent is running..."
            ):

                answer, trace = agent(
                    prompt,
                    mode,
                    c["bucket"],
                    c["secret_name"],
                    region,
                    model
                )

            st.session_state.trace = trace

            st.markdown(
                "### Agent Response"
            )

            st.code(
                answer,
                language="text"
            )

        except ClientError as e:

            st.error(
                f"AWS error: {e}"
            )

        except Exception as e:

            st.error(
                f"Demo error: {e}"
            )


# =========================================================
# RIGHT — TOOL TRACE
# =========================================================

with right:

    st.subheader("Tool Trace")

    label = {
        "VULNERABLE":
            "🔴 VULNERABLE — sensitive tool exposed",

        "HARDENED":
            "🟢 HARDENED — sensitive tool removed",

        "APPROVAL":
            "🟢 APPROVAL — sensitive action gated"
    }[mode]

    st.markdown(label)


    # -----------------------------------------------------
    # TRACE OUTPUT
    # -----------------------------------------------------

    for item in st.session_state.get(
        "trace",
        []
    ):

        # Sensitive disclosure
        if item.get("impact"):

            st.markdown(
                f"""
                <div class="impact">
                    ⚠️ <b>{item["tool"]}</b><br>
                    status: {item["status"]}<br>
                    <b>impact: {item["impact"]}</b>
                </div>
                """,
                unsafe_allow_html=True
            )

        else:

            st.markdown(
                f"""
                <div class="trace">
                    🔧 <b>{item["tool"]}</b><br>
                    status: {item["status"]}
                </div>
                """,
                unsafe_allow_html=True
            )


    # -----------------------------------------------------
    # CONFIG INFORMATION
    # -----------------------------------------------------

    st.divider()

    st.caption(
        f'S3: {c["bucket"]}'
    )

    st.caption(
        f'Secret: {c["secret_name"]}'
    )

    st.caption(
        f"Model: {model}"
    )