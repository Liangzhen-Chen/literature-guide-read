# Privacy

literature-guide-read collects nothing. It has no server, no account, no analytics and no telemetry, and the author receives no data from it.

- The scripts run on your machine (or in your agent's sandbox) and read only the PDF you give them. Everything they write stays in the working folder you choose.
- The only network request the scripts make is optional: when a paper has an arXiv identifier, `sources.py` downloads the paper's open version from arxiv.org. If the network is blocked, the skill carries on without it.
- The reading page is one offline HTML file. It loads nothing from the internet and sends nothing anywhere.
- The text of your PDF is read by the AI model your agent uses (Claude, Codex or another), under that provider's own privacy terms.

Questions: open an issue at https://github.com/Liangzhen-Chen/literature-guide-read/issues.
