import streamlit as st
import anthropic
import base64
import json
import re
 
st.set_page_config(page_title="Split the Bill", page_icon="🧾", layout="centered")
 
# ---------- Session state setup ----------
defaults = {
    "stage": "upload",       # upload -> review -> assign -> summary
    "line_items": [],        # list of {id, name, price}
    "tax": 0.0,
    "tip": 0.0,
    "subtotal_detected": 0.0,
    "people": [],            # list of names
    "claims": {},            # item_id -> set of person names
    "raw_receipt": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v
 
# Defensive guards: if state ever ends up the wrong type (e.g. from an old
# version of the app, a corrupted rerun, etc.), reset just that key instead
# of crashing the whole page.
if not isinstance(st.session_state.line_items, list):
    st.session_state.line_items = []
if not isinstance(st.session_state.people, list):
    st.session_state.people = []
if not isinstance(st.session_state.claims, dict):
    st.session_state.claims = {}
# Make sure every item is actually a dict with the expected keys
st.session_state.line_items = [
    it for it in st.session_state.line_items
    if isinstance(it, dict) and "id" in it and "name" in it and "price" in it
]
 
 
def get_api_key():
    """Pull the API key from Streamlit secrets, or ask the user for it."""
    if "ANTHROPIC_API_KEY" in st.secrets:
        return st.secrets["ANTHROPIC_API_KEY"]
    return st.session_state.get("api_key_input", "")
 
 
def reset_app():
    for k, v in defaults.items():
        st.session_state[k] = v
 
 
with st.sidebar:
    st.caption(f"Stage: `{st.session_state.stage}`")
    if st.button("🔄 Start over", use_container_width=True):
        reset_app()
        st.rerun()
 
 
def parse_receipt_with_claude(image_bytes, media_type, api_key):
    """Send the receipt image to Claude and get back structured item data."""
    client = anthropic.Anthropic(api_key=api_key)
    b64_image = base64.b64encode(image_bytes).decode("utf-8")
 
    prompt = """Look at this receipt image and extract the following as JSON only,
with no preamble, no markdown fences, no commentary:
 
{
  "items": [{"name": "...", "price": 0.00}],
  "subtotal": 0.00,
  "tax": 0.00,
  "tip": 0.00
}
 
Rules:
- "items" should be individual line items with their price (not multiplied by quantity --
  if quantity > 1, list it as a single item with the line total, and include the quantity in the name,
  e.g. "Margherita Pizza x2").
- If tip is not printed on the receipt, set "tip" to 0.00.
- If tax is not printed, set "tax" to 0.00.
- If subtotal is not printed, compute it as the sum of item prices.
- Use plain numbers for all prices (no currency symbols).
- Return ONLY the JSON object, nothing else.
"""
 
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64_image,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )
 
    text = "".join(block.text for block in response.content if block.type == "text")
    # Strip any accidental code fences just in case
    text = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    return json.loads(text)
 
 
def money(x):
    return f"${x:,.2f}"
 
 
# ============================================================
# STAGE: UPLOAD
# ============================================================
if st.session_state.stage == "upload":
    st.title("🧾 Split the Bill")
    st.write("Upload a photo of the receipt, or enter items manually.")
 
    api_key = get_api_key()
    if "ANTHROPIC_API_KEY" not in st.secrets:
        st.text_input(
            "Anthropic API key",
            type="password",
            key="api_key_input",
            help="Get one at console.anthropic.com. This is only used for this session and not stored.",
        )
        api_key = get_api_key()
 
    tab1, tab2 = st.tabs(["📷 Scan receipt", "✍️ Enter manually"])
 
    with tab1:
        uploaded = st.file_uploader(
            "Receipt photo", type=["jpg", "jpeg", "png", "webp"], key="uploader"
        )
        if uploaded is not None:
            st.image(uploaded, caption="Preview", use_container_width=True)
            if st.button("Scan receipt", type="primary", use_container_width=True):
                if not api_key:
                    st.error("Please enter an Anthropic API key above first.")
                else:
                    with st.spinner("Reading the receipt..."):
                        try:
                            media_type = uploaded.type or "image/jpeg"
                            data = parse_receipt_with_claude(
                                uploaded.getvalue(), media_type, api_key
                            )
                            items = []
                            for i, it in enumerate(data.get("items", [])):
                                items.append(
                                    {
                                        "id": f"item_{i}",
                                        "name": it.get("name", f"Item {i+1}"),
                                        "price": float(it.get("price", 0)),
                                    }
                                )
                            st.session_state.line_items = items
                            st.session_state.subtotal_detected = float(
                                data.get("subtotal", sum(it["price"] for it in items))
                            )
                            st.session_state.tax = float(data.get("tax", 0))
                            st.session_state.tip = float(data.get("tip", 0))
                            st.session_state.stage = "review"
                            st.rerun()
                        except json.JSONDecodeError:
                            st.error(
                                "Couldn't parse the receipt cleanly. Try a clearer photo, "
                                "or switch to manual entry."
                            )
                        except Exception as e:
                            st.error(f"Something went wrong: {e}")
 
    with tab2:
        st.write("Add items one at a time.")
        with st.form("manual_item_form", clear_on_submit=True):
            c1, c2 = st.columns([3, 1])
            name = c1.text_input("Item name")
            price = c2.number_input("Price", min_value=0.0, step=0.01, format="%.2f")
            added = st.form_submit_button("Add item")
            if added and name:
                idx = len(st.session_state.line_items)
                st.session_state.line_items.append(
                    {"id": f"item_{idx}", "name": name, "price": float(price)}
                )
 
        if st.session_state.line_items:
            st.write("**Items so far:**")
            for it in st.session_state.line_items:
                st.write(f"- {it['name']} — {money(it['price'])}")
 
            c1, c2 = st.columns(2)
            st.session_state.tax = c1.number_input(
                "Tax", min_value=0.0, step=0.01, format="%.2f", value=st.session_state.tax
            )
            st.session_state.tip = c2.number_input(
                "Tip", min_value=0.0, step=0.01, format="%.2f", value=st.session_state.tip
            )
 
            if st.button("Continue", type="primary", use_container_width=True):
                st.session_state.subtotal_detected = sum(
                    it["price"] for it in st.session_state.line_items
                )
                st.session_state.stage = "review"
                st.rerun()
 
 
# ============================================================
# STAGE: REVIEW (edit items/tax/tip before assigning)
# ============================================================
elif st.session_state.stage == "review":
    st.title("Review the receipt")
    st.caption("Fix anything that looks wrong before splitting.")
 
    new_items = []
    to_remove = []
    for i, it in enumerate(st.session_state.line_items):
        c1, c2, c3 = st.columns([3, 1, 0.5])
        name = c1.text_input("Name", value=it["name"], key=f"name_{it['id']}", label_visibility="collapsed")
        price = c2.number_input(
            "Price", value=float(it["price"]), step=0.01, format="%.2f",
            key=f"price_{it['id']}", label_visibility="collapsed",
        )
        remove = c3.button("✕", key=f"remove_{it['id']}")
        if remove:
            to_remove.append(it["id"])
        else:
            new_items.append({"id": it["id"], "name": name, "price": price})
 
    if to_remove:
        st.session_state.line_items = [it for it in new_items if it["id"] not in to_remove]
        st.rerun()
    else:
        st.session_state.line_items = new_items
 
    if st.button("+ Add item"):
        idx = len(st.session_state.line_items)
        st.session_state.line_items.append({"id": f"item_{idx}_{len(st.session_state.line_items)}", "name": "", "price": 0.0})
        st.rerun()
 
    st.divider()
    subtotal = sum(it["price"] for it in st.session_state.line_items)
    c1, c2 = st.columns(2)
    st.session_state.tax = c1.number_input(
        "Tax", min_value=0.0, step=0.01, format="%.2f", value=float(st.session_state.tax)
    )
    st.session_state.tip = c2.number_input(
        "Tip", min_value=0.0, step=0.01, format="%.2f", value=float(st.session_state.tip)
    )
 
    st.write(f"**Subtotal:** {money(subtotal)}  |  **Tax:** {money(st.session_state.tax)}  |  **Tip:** {money(st.session_state.tip)}")
    st.write(f"### Total: {money(subtotal + st.session_state.tax + st.session_state.tip)}")
 
    c1, c2 = st.columns(2)
    if c1.button("← Back", use_container_width=True):
        st.session_state.stage = "upload"
        st.rerun()
    if c2.button("Looks good →", type="primary", use_container_width=True):
        if not st.session_state.line_items:
            st.error("Add at least one item first.")
        else:
            st.session_state.stage = "people"
            st.rerun()
 
 
# ============================================================
# STAGE: PEOPLE (who's splitting this?)
# ============================================================
elif st.session_state.stage == "people":
    st.title("Who's splitting this?")
 
    with st.form("add_person", clear_on_submit=True):
        c1, c2 = st.columns([3, 1])
        new_name = c1.text_input("Name", label_visibility="collapsed", placeholder="Add a name")
        add = c2.form_submit_button("Add", use_container_width=True)
        if add and new_name.strip():
            if new_name.strip() not in st.session_state.people:
                st.session_state.people.append(new_name.strip())
 
    if st.session_state.people:
        st.write("**Group:**")
        for p in st.session_state.people:
            c1, c2 = st.columns([4, 1])
            c1.write(p)
            if c2.button("Remove", key=f"rm_person_{p}"):
                st.session_state.people.remove(p)
                st.rerun()
 
    st.divider()
    c1, c2 = st.columns(2)
    if c1.button("← Back", use_container_width=True):
        st.session_state.stage = "review"
        st.rerun()
    if c2.button("Continue →", type="primary", use_container_width=True):
        if len(st.session_state.people) < 1:
            st.error("Add at least one person.")
        else:
            st.session_state.stage = "assign"
            st.rerun()
 
 
# ============================================================
# STAGE: ASSIGN (who had what)
# ============================================================
elif st.session_state.stage == "assign":
    st.title("Who had what?")
    st.caption("Tap everyone who shared each item. Shared items split equally among those tapped.")
 
    for it in st.session_state.line_items:
        st.write(f"**{it['name']}** — {money(it['price'])}")
        claimed = st.session_state.claims.get(it["id"], set())
        cols = st.columns(len(st.session_state.people))
        for i, person in enumerate(st.session_state.people):
            is_claimed = person in claimed
            label = f"✅ {person}" if is_claimed else person
            if cols[i].button(label, key=f"claim_{it['id']}_{person}", use_container_width=True):
                claimed = set(claimed)
                if person in claimed:
                    claimed.remove(person)
                else:
                    claimed.add(person)
                st.session_state.claims[it["id"]] = claimed
                st.rerun()
        if not claimed:
            st.caption("⚠️ Nobody assigned to this item yet")
        st.divider()
 
    unassigned = [it for it in st.session_state.line_items if not st.session_state.claims.get(it["id"])]
 
    c1, c2 = st.columns(2)
    if c1.button("← Back", use_container_width=True):
        st.session_state.stage = "people"
        st.rerun()
    if c2.button("Calculate split →", type="primary", use_container_width=True, disabled=bool(unassigned)):
        st.session_state.stage = "summary"
        st.rerun()
    if unassigned:
        st.warning(f"{len(unassigned)} item(s) still need someone assigned before you can continue.")
 
 
# ============================================================
# STAGE: SUMMARY (final tally + who pays who)
# ============================================================
elif st.session_state.stage == "summary":
    st.title("💰 The Tally")
 
    subtotal = sum(it["price"] for it in st.session_state.line_items)
    tax = st.session_state.tax
    tip = st.session_state.tip
    total = subtotal + tax + tip
 
    # Proportionally allocate tax & tip based on each person's share of the subtotal
    person_subtotal = {p: 0.0 for p in st.session_state.people}
    for it in st.session_state.line_items:
        claimed = st.session_state.claims.get(it["id"], set())
        if claimed:
            share = it["price"] / len(claimed)
            for p in claimed:
                person_subtotal[p] += share
 
    person_total = {}
    for p in st.session_state.people:
        if subtotal > 0:
            proportion = person_subtotal[p] / subtotal
        else:
            proportion = 1 / len(st.session_state.people)
        person_total[p] = person_subtotal[p] + proportion * (tax + tip)
 
    # Display per-person breakdown
    for p in st.session_state.people:
        with st.container(border=True):
            c1, c2 = st.columns([2, 1])
            c1.write(f"**{p}**")
            c2.write(f"### {money(person_total[p])}")
            their_items = [
                it for it in st.session_state.line_items
                if p in st.session_state.claims.get(it["id"], set())
            ]
            if their_items:
                lines = []
                for it in their_items:
                    n_sharing = len(st.session_state.claims[it["id"]])
                    if n_sharing > 1:
                        lines.append(f"{it['name']} (split {n_sharing} ways) — {money(it['price']/n_sharing)}")
                    else:
                        lines.append(f"{it['name']} — {money(it['price'])}")
                st.caption(" · ".join(lines))
            st.caption(f"includes {money(person_subtotal[p]/subtotal*tax) if subtotal else 0} tax + {money(person_subtotal[p]/subtotal*tip) if subtotal else 0} tip")
 
    st.divider()
    c1, c2, c3 = st.columns(3)
    c1.metric("Subtotal", money(subtotal))
    c2.metric("Tax", money(tax))
    c3.metric("Tip", money(tip))
    st.write(f"### Total: {money(total)}")
 
    check = sum(person_total.values())
    if abs(check - total) > 0.02:
        st.warning(f"Rounding check: split totals to {money(check)}, receipt total is {money(total)}.")
 
    st.divider()
    c1, c2 = st.columns(2)
    if c1.button("← Edit assignments", use_container_width=True):
        st.session_state.stage = "assign"
        st.rerun()
    if c2.button("🔄 Start a new bill", use_container_width=True):
        reset_app()
        st.rerun()