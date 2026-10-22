// Sends the question to POST /ask and shows the loop's trace and final answer.

const form = document.getElementById("ask-form");
const input = document.getElementById("question");
const button = document.getElementById("ask-button");
const stepsList = document.getElementById("steps");
const answerBox = document.getElementById("answer");

form.addEventListener("submit", async function (event) {
  event.preventDefault(); // handle the submit here instead of reloading the page

  const question = input.value.trim();
  if (question === "") {
    return;
  }

  button.disabled = true;
  stepsList.replaceChildren();
  answerBox.textContent = "Thinking...";

  try {
    const response = await fetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: question }),
    });
    const data = await response.json().catch(function () {
      return {}; // a Flask crash page is HTML, not JSON
    });

    if (!response.ok) {
      answerBox.textContent = "Error: " + (data.error || "request failed (" + response.status + ")");
      return;
    }

    for (const line of data.steps) {
      const item = document.createElement("li");
      item.textContent = line; // textContent, never innerHTML: model output is untrusted text
      stepsList.appendChild(item);
    }
    answerBox.textContent = data.answer === null ? "(no final answer)" : data.answer;
  } catch (error) {
    answerBox.textContent = "Error: could not reach the UI server.";
  } finally {
    button.disabled = false;
  }
});
