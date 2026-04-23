from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse


router = APIRouter()


BASE_STYLE = """
    :root {
      color: #182421;
      background: #f2ede1;
      font-family: Georgia, "Times New Roman", serif;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      grid-template-rows: auto 1fr auto;
      background:
        radial-gradient(circle at 20% 20%, rgba(217, 96, 54, 0.2), transparent 28rem),
        radial-gradient(circle at 80% 10%, rgba(40, 118, 108, 0.18), transparent 24rem),
        linear-gradient(145deg, #f2ede1 0%, #d7e2d8 100%);
    }

    .top-banner,
    .bottom-banner {
      width: min(72rem, 100%);
      margin: 0 auto;
      padding: 1rem clamp(1rem, 4vw, 2rem);
    }

    .top-banner {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
    }

    .brand {
      color: #182421;
      font-size: 1.1rem;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-decoration: none;
      text-transform: uppercase;
    }

    .home-link {
      border: 1px solid rgba(24, 36, 33, 0.18);
      border-radius: 999px;
      padding: 0.55rem 0.9rem;
      color: #182421;
      background: rgba(255, 252, 244, 0.72);
      text-decoration: none;
    }

    .home-link:hover,
    .home-link:focus {
      color: #fffaf0;
      background: #c94f2d;
      outline: none;
    }

    .page-shell {
      width: min(72rem, 100%);
      margin: 0 auto;
      padding: clamp(1rem, 4vw, 2rem);
      display: grid;
      place-items: center;
    }

    main {
      width: min(48rem, 100%);
      padding: clamp(1.25rem, 5vw, 2.25rem);
      border: 1px solid rgba(24, 36, 33, 0.14);
      border-radius: 1.5rem;
      background: rgba(255, 252, 244, 0.88);
      box-shadow: 0 1.5rem 4rem rgba(24, 36, 33, 0.16);
    }

    h1 {
      margin: 0 0 0.75rem;
      font-size: clamp(2.25rem, 9vw, 4.5rem);
      line-height: 0.92;
      letter-spacing: -0.05em;
    }

    p {
      margin: 0 0 1.5rem;
      color: #5d6f69;
    }

    .bottom-banner {
      color: #5d6f69;
      font-size: 0.95rem;
    }

    @media (max-width: 36rem) {
      .top-banner {
        align-items: flex-start;
        flex-direction: column;
      }

      .home-link {
        width: 100%;
        text-align: center;
      }
    }
"""


def _page(title: str, body: str, extra_style: str = "") -> str:
    return f"""
<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
{BASE_STYLE}
{extra_style}
  </style>
</head>
<body>
  <header class="top-banner">
    <a class="brand" href="/">Button Clicker RPI</a>
    <a class="home-link" href="/">Home</a>
  </header>
  <div class="page-shell">
{body}
  </div>
  <footer class="bottom-banner">Button Clicker RPI local control panel</footer>
</body>
</html>
"""


@router.get("/", response_class=HTMLResponse)
def home_page() -> str:
    return _page(
        "Button Clicker RPI",
        """
    <main>
      <h1>Button Clicker RPI</h1>
      <p>Choose a page to inspect device info or send a touch request.</p>
      <nav class="home-nav" aria-label="Application pages">
        <a href="/info">Information<span>Show serial number and machine status.</span></a>
        <a href="/test">Test<span>Open the touch test button.</span></a>
      </nav>
    </main>
""",
        """
    .home-nav {
      display: grid;
      gap: 1rem;
    }

    .home-nav a {
      display: block;
      padding: 1.1rem 1.25rem;
      border-radius: 1rem;
      color: #fffaf0;
      background: #182421;
      text-decoration: none;
      font-size: 1.25rem;
      box-shadow: 0 0.75rem 1.5rem rgba(24, 36, 33, 0.16);
    }

    .home-nav a:hover,
    .home-nav a:focus {
      background: #c94f2d;
      outline: none;
    }

    .home-nav span {
      display: block;
      margin-top: 0.25rem;
      color: rgba(255, 250, 240, 0.72);
      font-size: 0.95rem;
    }
""",
    )


@router.get("/info", response_class=HTMLResponse)
def info_page() -> str:
    return _page(
        "Button Clicker Info",
        """
    <main>
      <h1>Device Info</h1>
      <section class="status-grid" id="statusGrid" aria-live="polite">
        <article class="status-card">
          <span class="label">Status</span>
          <span class="value">Loading...</span>
        </article>
      </section>
    </main>

    <script>
      const statusGrid = document.querySelector("#statusGrid");

      function boolText(value, trueText, falseText) {
        return value ? trueText : falseText;
      }

      function statusClass(value) {
        return value ? "ok" : "bad";
      }

      function card(label, value, className = "") {
        return `
          <article class="status-card">
            <span class="label">${label}</span>
            <span class="value ${className}">${value}</span>
          </article>
        `;
      }

      async function loadInfo() {
        try {
          const response = await fetch("/api/info");
          if (!response.ok) {
            throw new Error("Unable to load device information.");
          }

          const data = await response.json();
          const info = data.data || {};
          const cards = [
            card("Serial Code", info.serial_code || "-"),
            card(
              "Service Connection",
              boolText(info.connection, "Connected", "Disconnected"),
              statusClass(info.connection)
            )
          ];

          if (info.connection) {
            cards.push(
              card(
                "Machine Verification",
                boolText(info.verified, "Registered", "Not Registered"),
                statusClass(info.verified)
              )
            );
          }

          statusGrid.innerHTML = cards.join("");
        } catch (error) {
          statusGrid.innerHTML = card("Status", error.message || String(error), "bad");
        }
      }

      loadInfo();
    </script>
""",
        """
    .status-grid {
      display: grid;
      gap: 1rem;
      grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
    }

    .status-card {
      padding: 1rem;
      border: 1px solid rgba(23, 49, 43, 0.12);
      border-radius: 1rem;
      background: rgba(238, 242, 234, 0.72);
    }

    .label {
      display: block;
      margin-bottom: 0.35rem;
      color: #587065;
      font-size: 0.9rem;
    }

    .value {
      display: block;
      color: #17312b;
      font-size: 1.35rem;
      overflow-wrap: anywhere;
    }

    .ok {
      color: #1f7a4a;
    }

    .bad {
      color: #b93232;
    }
""",
    )


@router.get("/test", response_class=HTMLResponse)
def test_page() -> str:
    return _page(
        "Button Clicker Test",
        """
    <main>
      <h1>Touch Test</h1>
      <button id="touchButton" type="button">Touch</button>
      <p class="touch-status" id="result" aria-live="polite">Waiting for input.</p>
    </main>

    <script>
      const button = document.querySelector("#touchButton");
      const result = document.querySelector("#result");

      button.addEventListener("click", async () => {
        button.disabled = true;
        result.className = "touch-status";
        result.textContent = "Sending request...";

        try {
          const response = await fetch("/api/touch", { method: "POST" });
          if (!response.ok) {
            throw new Error("Touch request failed.");
          }

          const data = await response.json();
          if (data.error) {
            throw new Error("Touch request returned an error.");
          }

          result.className = "touch-status ok";
          result.textContent = "Touch request sent successfully.";
        } catch (error) {
          result.className = "touch-status bad";
          result.textContent = error.message || String(error);
        } finally {
          button.disabled = false;
        }
      });
    </script>
""",
        """
    button {
      width: 100%;
      border: 0;
      border-radius: 999px;
      padding: 1rem 1.25rem;
      color: #fffaf0;
      background: #c94f2d;
      font: inherit;
      font-size: 1.25rem;
      cursor: pointer;
      box-shadow: 0 0.75rem 1.5rem rgba(201, 79, 45, 0.22);
    }

    button:disabled {
      cursor: wait;
      opacity: 0.68;
    }

    .touch-status {
      margin: 1rem 0 0;
      padding: 1rem;
      border-radius: 1rem;
      background: rgba(16, 32, 47, 0.08);
      color: #10202f;
    }

    .ok {
      color: #1f7a4a;
    }

    .bad {
      color: #b93232;
    }
""",
    )
