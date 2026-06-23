# Split the Bill 🧾

Snap a photo of a receipt, let Claude read off the items/tax/tip, then have everyone
tap what they ordered. The app works out who owes what (tax & tip are split
proportionally to what each person ordered).

## How it works

1. **Upload** a receipt photo (or type items in manually)
2. **Review** the extracted items, tax, and tip — fix anything Claude misread
3. **Add people** in your group
4. **Assign** — tap everyone who shared each item
5. **Tally** — see exactly what each person owes

## Run it locally

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# edit .streamlit/secrets.toml and paste in your Anthropic API key
streamlit run app.py
```

Get an API key at [console.anthropic.com](https://console.anthropic.com).

If you skip the secrets file, the app will just ask you to paste a key into a
text box at runtime instead (it's used only for that session, never saved).

## Deploy to Streamlit Community Cloud

1. Push this folder to a GitHub repo
2. Go to [share.streamlit.io](https://share.streamlit.io) → "New app" → point it at
   your repo and `app.py`
3. In the app's **Settings → Secrets**, paste:
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-your-key-here"
   ```
4. Deploy. Share the URL with your friends — everyone can open it on their own phone.

## Notes on splitting logic

- Each item can be claimed by one or more people (equal split among claimers)
- Tax and tip are allocated proportionally: if you ordered 30% of the subtotal,
  you pay 30% of the tax and tip too
- The app flags any item nobody has claimed before letting you move to the final tally

## Cost

Each receipt scan is one Claude API call (a single image + short prompt) —
typically a fraction of a cent per receipt.
