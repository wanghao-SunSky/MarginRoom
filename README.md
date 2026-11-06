# MarginRoom · 阅间

**A reading tool for the AI era — an AI-native workspace built from the ground up for reading difficult books together.**

[English](README.md) · [简体中文](README.zh-CN.md) · **[Try Online Free (marginroom.app)](https://marginroom.app)**

Try the hosted reader with official Rust Book excerpts and **3 real AI questions, no signup required**. Sign in afterward to keep your reading records.

When you are working through a dense textbook, a technical monograph, or a long paper, what breaks your flow is rarely a single word—it is **losing the thread**. A proof in Chapter 5 quietly relies on a notation introduced in Chapter 2; you follow the algebra line by line, yet lose sight of the problem the chapter is actually trying to solve; you finally conquer a tough section, close the window, and forget half of it by next week. When a chat box sits detached from your reading state, you still end up scrolling back and forth, hunting through the table of contents, and copy-pasting paragraphs just to give an AI enough context to help.

In **MarginRoom**, the Agent actually lives inside the book with you:
- **Anchored to your open section & selection**: It automatically receives the section or PDF page you have open and the exact passage you highlighted—no copy-pasting required.
- **Reads across the entire book on demand**: It can inspect the full table of contents, run keyword searches across chapters, pull up any section or whole chapter to verify a claim, and even search your past conversations in the same book.
- **Drives the reader view with you**: Ask *"Where was this assumption introduced? Take me there,"* and the Agent will locate the earlier chapter, flip your reader directly to that section or page, wait for the page to settle, and explain how the pieces connect. One click brings you right back to where you were reading.
- **Distills finished sections into notes & Anki cards**: Just finished a demanding section? Have the Agent turn the core ideas into cited notes or comprehension-focused flashcards—test yourself in place, polish the wording inline, and download an Anki .apkg package or TSV file to import.

![MarginRoom reading workspace](docs/images/reading-en.jpg)

---

## What Reading Together Looks Like

Picture yourself halfway through a systems book or a machine learning tutorial when you hit a wall:

1. **Highlight and ask right where you are stuck**  
   Select a dense paragraph and click **Explain selection**, or simply ask in place: *"Why does this step suddenly require this constraint?"* Because the Agent already holds your open section and highlighted quote, it can focus directly on the passage and examples in front of you—attaching clickable section citations so you can verify every reference against the page.

2. **Trace ideas across chapters—and let the Agent take you there**  
   Follow up naturally: *"Find where the author first defined this boundary condition, jump me there, and walk me through how it leads to this theorem."*  
   The Agent searches the book, reads the earlier section to verify, and **navigates your reading pane directly to that chapter or PDF page** (waiting for the reader's acknowledgement before continuing). Once you've read the original context side by side, hit **Return to reading position**—or ask the Agent to take you back—and pick up right where you left off.

3. **Zoom out to the big picture & track real progress**  
   Lost in the weeds? Ask *"Read this chapter and map out the core problem it solves,"* or *"Check the table of contents—how does this section set up what comes next?"* As you mark sections as read, the Agent can inspect your recorded progress, saved notes, and past questions to compile a grounded **Reading Review**—summarizing the sections you've marked read, the notes you've kept, and the questions you've explored so you can see what is still open and what to revisit next.

4. **Lock in understanding with inline flashcards & Anki export**  
   When a section finally clicks, click **Create cards** or ask: *"Break the key mechanism in this section into 4 flashcards that test understanding, not rote definitions."*  
   Draft cards appear in the **Flashcards** tab—one focused question per card. Try answering in your head before clicking to reveal the back, edit any question or answer inline (changes auto-save on blur), jump back to the exact source passage anytime, and export your deck as an **Anki .apkg** package (templates included) or **TSV** file, or export your notes and discussions as **Markdown**.

---

## Why MarginRoom Feels Different

MarginRoom brings reading, whole-book lookup, live page navigation, and export-ready review cards into a single workspace built around **how people actually read and retain hard material**:

- **A unified three-pane reading studio**: A searchable outline with automatic reading progress and manual overrides on the left; clean, book-grade typography in the center (full Markdown, LaTeX math, formatted code blocks, a one-click toggle between **Original PDF** layout and **Extracted text**, plus continuous scrolling by default, with section-by-section layout and automatic progress available in Reading settings); and your companion chat, notes, and flashcard deck on the right. Switch the UI and new AI reply language anytime via `中文 | EN` in the top bar.
- **Inspectable tool trace & clickable citations**: Every time the Agent checks the outline, reads a chapter, or searches earlier discussions, you can expand its activity trace above the reply. System prompts guide the Agent to distinguish source evidence from its own inferences, and `[Section Title]` citations that match real sections in your current book render as live buttons that jump your reader straight to the source page for verification.
- **Respects your reading pace**: While an explanation is streaming in, clicking inside the chat or scrolling up immediately pauses auto-scrolling so the text never yanks away from under your eyes. Click **Jump to latest** whenever you are ready to catch up.

---

## Start Reading (Online or Localhost)

- **Hosted Web App ([marginroom.app](https://marginroom.app))**: Open in your browser with zero setup or API key configuration. Sign in with an email verification code or Google to get **50 free AI questions per user per day** (service-wide usage limits also apply). On the hosted service, your library, reading progress, notes, flashcards, and conversations are stored in your cloud account on the server.
- **Self-Hosted Local Edition (this repository)**: Runs as a single-user app on your machine (`127.0.0.1`) using your own DeepSeek, OpenAI-compatible, or Claude API configuration. Your library, reading positions, read marks, notes, flashcards, and conversation history live on disk under `data/` in SQLite (account login, email verification, OAuth, and hosted quota management are not part of the open-source local edition).

### Prerequisites
- **Python 3.12+** and **[uv](https://docs.astral.sh/uv/getting-started/installation/)**
- **Node.js 22.13+** (or Node.js 24+, matching the current Vite and PDF renderer requirements) and **npm**
- A **DeepSeek, OpenAI-compatible, or Claude API key** *(optional at first launch—you can browse the built-in samples, import documents, read, and take manual notes without a key; add one whenever you're ready for AI co-reading)*

### Install & Launch


```sh
git clone https://github.com/wanghao-SunSky/MarginRoom.git
cd MarginRoom

# 1. Install Python dependencies & securely configure your model API (hidden input, stored only in server .env)
uv sync
uv run python scripts/configure_model.py

# 2. Build frontend assets (if needed) and start the local server (macOS / Linux)
./scripts/start.sh
```

On Windows—or if you prefer running each step manually:

```sh
cd web
npm ci
npm run build
cd ..
uv run uvicorn backend.app:app --host 127.0.0.1 --port 8765
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765) in your browser. MarginRoom ships with two original quick-start essays (in English and Chinese) so you can immediately try highlighting a passage, jumping across sections, and generating Anki cards—then import your own **PDF, EPUB, MOBI, AZW3, Markdown (`.md`), or UTF-8 TXT** books and papers.

Local MOBI/AZW3 imports require `mobitool`: install with `brew install libmobi` on macOS or `sudo apt-get install libmobi-tools` on Debian/Ubuntu. EPUB imports do not require it.

> **Models & configuration**: Choose DeepSeek, an OpenAI-compatible Chat Completions endpoint, or the native Claude Messages API. Configure base URL, model ID, key, and optional reasoning effort with the setup wizard or `.env`. Existing `DEEPSEEK_*` settings remain supported. See [Model configuration](docs/model-configuration.md) for examples and compatibility notes. Set `READING_PORT` to change the local port.

---

## Importing Flashcards into Anki

Click **Anki .apkg** for a package with a note type, front/back templates, stable note GUIDs, and source links. The official Anki import engine has been checked for initial import, duplicate reimport, and updates to newer versions of the same notes. Desktop/mobile GUI import and clicking source links have not been tested; Anki normally updates only newer note versions. TSV remains available for custom workflows:

Click **Anki TSV** in the Flashcards tab to download a tab-separated file with `#separator:Tab`, `#html:true`, a `#columns:` header matching your active UI language, and a stable card `ID` in the first column:

1. In desktop Anki, create a Note Type with five fields in order:
   - **When exported in English (`EN`) UI**: `ID`, `Question`, `Answer`, `Source`, `Tags`
   - **When exported in Chinese (`中文`) UI**: `ID`, `问题`, `答案`, `来源`, `标签`
2. Import the downloaded `.tsv` file with **Allow HTML in fields** enabled and verify the field mapping matches the five columns above. If you plan to re-export and update existing cards later, set Anki's import **Existing notes** option to update when matching the first field (`ID`)—deduplication behavior depends on the matching rule selected in Anki's import dialog.
3. Suggested card template (matching your Note Type's field names):
   - For English field names (`ID` / `Question` / `Answer` / `Source` / `Tags`):
     ```html
     <!-- Front -->
     {{Question}}

     <!-- Back -->
     {{FrontSide}}<hr id="answer">{{Answer}}<br><small>{{Source}}</small>
     ```
   - For Chinese field names (`ID` / `问题` / `答案` / `来源` / `标签`):
     ```html
     <!-- 正面 -->
     {{问题}}

     <!-- 背面 -->
     {{FrontSide}}<hr id="answer">{{答案}}<br><small>{{来源}}</small>
     ```
   When you open a card's source link in the environment where it was exported (with your local MarginRoom server running for local exports, or signed into `marginroom.app` for hosted exports), your browser opens that exact section or PDF page.

---

## How It Works, Privacy & Honest Boundaries

So you always know what happens under the hood:

- **How whole-book context & progress work**: MarginRoom doesn't stuff an entire book into every prompt or rely on opaque background embeddings. Each question automatically carries your **open section (up to 16,000 chars), highlighted passage (up to 5,000 chars), and recent conversation**, while the Agent uses bounded tool calls to inspect the outline, run keyword searches across the book and chat history, and read specific sections or chapters on demand (up to ~46,000 chars per chapter call, disclosing if truncated). Position tracking follows your open section/PDF page and selection; progress uses visible, foreground reading time and coverage, with manual read/unread overrides. Read marks are not evidence of mastery.
- **Personal learning records**: Selected passages saved as notes keep a light underline at the exact occurrence; changed material or unverifiable old notes are not guessed into place. Optional “Explain it in your own words” feedback checks your explanation against the current source and suggests up to two editable cards for you to confirm. Section starters use cached source content; small, dismissible history reminders use keyword overlap rather than per-paragraph model calls.
- **Recovery and validation**: Interrupted replies retain received prose and reconnect to the same run. Tool progress reflects returned results; bounded reading reports covered sections and gaps. Invalid citations lose their links while readable prose stays visible; an existing section link does not establish sentence-level factual accuracy. Real iPhone/iPad interaction and PDF touch selection remain untested. No in-app spaced-repetition scheduler is included.
- **Supported files & PDFs**: Supports **PDF, EPUB, MOBI, AZW3, Markdown, and UTF-8 TXT** (20 MB per file; unencrypted PDFs: 600 pages locally, 200 on the hosted service). EPUB/Kindle imports preserve reading order, navigation, common raster images, and internal links. Reflowable, DRM-free ebooks are supported; original publisher CSS is not retained. PDFs provide both an original-page view and extracted text, **without OCR or image/diagram vision**—scanned or image-only pages are flagged clearly so you can view them in Original PDF mode.
- **Privacy & network scope**: In the open-source local edition (`127.0.0.1`, single-user, do not expose directly to the public internet), your data and `.env` API key stay on your machine, and only when you ask an AI question or request explanation feedback does the local backend send the relevant reading context and tool-retrieved book excerpts to your configured model provider. On the hosted web service (`marginroom.app`), your uploaded documents, notes, flashcards, and chat history are stored on the service's servers under your account, and asking an AI question sends the relevant reading excerpts to the configured model provider. See [Architecture](docs/architecture.md) and [Security & Privacy](SECURITY.md) for details.

## Development & Checks

```sh
uv run pytest -q
cd web && npm test && npm run build
```

For frontend hot-reload during development, keep the FastAPI backend running on port `8765` and run `cd web && npm run dev` (Vite serves on `127.0.0.1:5178` and proxies `/api`). See [Contributing](CONTRIBUTING.md) and [Release Checks](docs/release-checks.md).

Released under the [MIT License](LICENSE).
