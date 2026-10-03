# The Last Crossing

A small terminal adventure for one player and one NPC, with a separate Narrator. Convince Maren,
a wary harbor-master, to lend you a rescue key before the tide turns. No graphics.

[Visual guide to the plot, Maren's reactions, and the path to the key](how-it-works.html).

## Play

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/javiercancela/ConvGame.git
cd ConvGame
uv sync
```

Start your existing Bonsai installation in a separate terminal:

```bash
cd /home/xavi/Projects/Bonsai
./scripts/start_llama_server.sh
```

Then configure your [TypeSafe API key](https://console.typesafe.ai) and play:

```bash
cd /home/xavi/Projects/ConvGame
read -rsp 'TypeSafe API key: ' TYPESAFE_API_KEY
export TYPESAFE_API_KEY
uv run convgame --check
uv run convgame
```

The key prompt hides input and avoids putting the key in shell history. Environment
variables are read directly; terminal commands do not automatically load `.env` files. `--check`
checks key presence and the local model endpoint, without sending a paid Jev request.

Describe physical actions such as `I read the ledger`. To speak, explicitly address
Maren (`Maren, can I borrow the key?`), describe speaking (`I say to Maren, "I'll
bring it back."`), or enter a standalone spoken quotation. Bare requests and
promises are not automatically treated as speech; private thoughts cannot persuade him.
The **Narrator** describes actions and observable outcomes. **Maren** speaks when
addressed or when a significant action provokes a response. Reading an object
does not require him to comment, and asking about the ledger does not count as reading it.

An action and speech can share a line, for example `I read the ledger and tell Maren
I'll take a rope, use the east steps, and return the key.` Physical actions resolve
before accompanying speech; preparing the plan and asking for the key in the same
turn still cannot win. Supported physical actions are inspecting the three scene
objects, ringing the bell, and attempting to take the guarded key.

Commands `/look`,
`/status`, `/help`, and `/quit` are free; each evaluated line uses one of twelve
turns, including clarifications and off-world remarks. EOF and Ctrl+C exit cleanly.

Try these lines for a short winning game:

```text
I read the ledger.
Maren, I promise to take a rope, use the east steps, and return your key.
Maren, please lend me the key.
```

Jev's interpretations and confidence may require clarification or another reassurance.
Threatening Maren repeatedly can end the encounter early.

## How it works

1. [Jev's Python SDK](https://docs.typesafe.ai/sdk/python) receives the scene,
   current world, six recent messages with labeled narration and speech, and the player's line in **one
   `system_one` call**. Eleven independent questions cover physical action and its
   object, explicit speech recipient, spoken intent and its object,
   off-world dialogue, safe-plan commitment, key handover, tension,
   hostility, and reassurance. SDK retries are disabled to keep one attempt per turn.
2. Python gates discrete actions on Choice confidence (default `0.6`). It uses
   Noul probabilities to adjust trust/suspicion and a normalized, confidence-gated
   tension Score for composure. Noul has no confidence field. Ambiguity produces
   a Narrator clarification; off-world remarks and private intentions do not change
   emotional dials; quiet inspections also leave Maren's mood unchanged.
   Reassurance and promises require explicit speech to Maren;
   observable hostile actions can affect him without spoken words.
3. Python selects ordered response beats with explicit speakers, then sends the
   resulting state and directive to Bonsai's local `/v1/chat/completions` endpoint.
   Clarifications, unspoken intentions, and off-world remarks use fixed Narrator
   guidance. Lines without accepted speech are omitted from dialogue memory;
   their narrated outcomes remain available as context.
   The same model writes both voices as structured JSON, using llama.cpp's
   [schema-constrained response format](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md#json-schemas--gbnf)
   to fix the speakers, order, and sentence count. Thinking is disabled;
   each beat contains one or two complete sentences and at most 65 words, with
   100 words allowed across the whole response. Missing, extra, reordered, or
   unauthorized speakers, malformed JSON, and incomplete or oversized text fall
   back to a scripted response with the same narration and speech structure.

To win, the ledger must have been read, the safety plan agreed, trust must be at
least 55%, and suspicion below 65% **before** the request for the key. Jev must
also confidently identify a peaceful handover request. Python checks these rules
again before awarding the key. Physical grabs are blocked even when you are ready.
Generated prose cannot mutate state; `/status`
and the terminal ending are authoritative. As with any prompted narrator, prose
may occasionally contradict the directive; it is not semantically re-evaluated.

Jev failures leave the turn and world unchanged. Bonsai failures use a clearly
announced scripted response after the resolved action, so retrying does not apply
an action twice.
Game state is in memory; quitting starts a new encounter next time.

## Configuration and development

```bash
uv run convgame --debug                        # decisions, state, per-service timings
uv run convgame --log-file logs/my-game.jsonl   # choose the execution log path
uv run convgame --bonsai-url http://127.0.0.1:8081
uv run convgame --jev-model jev-latest --confidence 0.6
uv run pytest
```

`BONSAI_URL` defaults to `http://127.0.0.1:8080` (a trailing `/v1` is also accepted).
`BONSAI_CHAT_MODEL` optionally sets the served model's API identifier; normally
llama-server selects its loaded model. `TYPESAFE_DEFAULT_MODEL` selects Jev.
Use the Bonsai repository's runtime for its weights, not stock llama.cpp.

The `world/` package separates state and decision types, directive constants,
confidence checks, emotion changes, actions, and outcomes. The `jev/` package separates the client,
question builder, response validation, and scene and question constants.
`bonsai.py` owns local narration and dialogue generation, and `cli.py` connects them.
Tests cover mechanics, confidence gates, the actual SDK response shapes using a
mock HTTP transport, Bonsai's HTTP contract, and a complete game with test doubles.

Every invocation, including `--check`, appends an execution log to
`logs/convgame.jsonl` and prints its location. Use `--log-file PATH` to choose another
file. Each line is a JSON object with a UTC timestamp, session identifier, event,
and plain-language `reason`. Evaluated input also has an `attempt` and intended
`turn`, so a failed Jev call and its retry are distinguishable.

The log includes Jev's scene, state, player line, questions, returned answers and
confidence/probabilities; Bonsai's prompts, generation settings, response schema,
returned response and call timings; and Python's confidence checks, emotion
changes, action/speech decisions, safety-plan and key-handover requirements,
endings, selected response beats, fallbacks, and final state. Reasons describe
the program's actual rule branches. API keys, authorization headers, and provider
exception bodies are not recorded. Player text and model responses are recorded;
the default `logs/` directory is excluded from Git.

To watch the log while playing:

```bash
tail -f logs/convgame.jsonl
```

### Debug in Visual Studio Code

Open this project folder in VS Code and install the recommended Python and Python
Debugger extensions if prompted. In **Run and Debug**, select **ConvGame: Play**,
set a breakpoint in `convgame/cli.py` or `convgame/world/turn.py`, and press
**F5**. Enter game dialogue in the integrated terminal. The launch runs
`uv sync --locked` and uses the project's `.venv` interpreter; `uv` must be on PATH.
The launch configuration enables the game's `--debug` diagnostics. Start Bonsai
as described above and put your settings in a local `.env` file in the project root:

```dotenv
TYPESAFE_API_KEY=your-api-key
BONSAI_URL=http://127.0.0.1:8080
```

The debugger loads this file, which is already excluded by `.gitignore`.
It can also use variables inherited by VS Code. Play uses the TypeSafe API
as described below. Tests are available in VS Code's **Testing** view, where you
can run or debug individual tests.

Live play sends the scene and recent messages to TypeSafe. Narration and NPC text generation
uses the configured Bonsai endpoint, which is local by default.
