# Grok Supabase builder

This repository includes a Grok Build coding-bot launcher and a project-scoped
Supabase MCP configuration for `ngoxpbvmhxdrqtfgqpna`. It can inspect the database
and implement requested features using Supabase tools and the local checkout.
It is a local coding bot, not a hosted Grok Bot account or a dashboard chat widget.

## First launch

Install Grok Build using the [official guide](https://docs.x.ai/build/overview).
The documented macOS/Linux installer is:

```sh
curl -fsSL https://x.ai/cli/install.sh | bash
```

From the repository root:

```sh
python3 scripts/grok-bot.py
```

Sign in to Grok when prompted. In Grok, open `/mcps` and authenticate the
`supabase` server through its browser OAuth flow. Then verify:

```sh
python3 scripts/grok-bot.py --doctor
```

The launcher always runs from this repository so Grok discovers
`.grok/config.toml`, including when you invoke the script by absolute path.
Project configuration takes precedence over a user server with the same name.
No API key or access token belongs in the committed config. OAuth credentials
are managed by Grok in your user profile.

## Give it work

```sh
python3 scripts/grok-bot.py "Build an authenticated case notes feature with an RLS-protected Supabase table, a versioned migration, and dashboard integration."
python3 scripts/grok-bot.py --headless "Inspect the schema and identify missing indexes; report findings without changing the database."
python3 scripts/grok-bot.py --dry-run "Inspect the Supabase schema"
```

Interactive mode is the default. Complete sign-in and MCP OAuth interactively
before headless use. The launcher keeps Grok's normal tool approval behavior.
The bot's instructions are in `bots/supabase-builder.md`.

Optional Supabase skills can be installed from this directory with
`npx skills add supabase/agent-skills`; choose Grok as the target if offered.
These skills are not required by the launcher and have not been installed here.

References: [MCP setup and OAuth](https://docs.x.ai/build/features/mcp-servers),
[Grok CLI flags](https://docs.x.ai/build/cli/reference).
