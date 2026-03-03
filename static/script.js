document.getElementById("add-url-btn").addEventListener("click", addURL);
document.getElementById("add-image-btn").addEventListener("click", addImage);
document.getElementById("ask-btn").addEventListener("click", askQuestion);

// -------------------- ADD MENU FROM URL --------------------
async function addURL() {
  const url = document.getElementById("menu-url").value.trim();
  if (!url) return alert("Please enter a URL");

  try {
    const res = await fetch("/import_menu", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url })
    });

    const data = await res.json();

    if (!res.ok) {
      document.getElementById("response").innerText =
        data.message || "Failed to import menu.";
      return;
    }

    document.getElementById("response").innerText =
      `Menu added successfully.\nItems added: ${data.items || "N/A"}`;
  } catch (error) {
    document.getElementById("response").innerText = "Error importing menu.";
    console.error(error);
  }
}

// -------------------- ADD MENU FROM IMAGE --------------------
async function addImage() {
  const fileInput = document.getElementById("menu-image");
  if (!fileInput.files.length) return alert("Please select an image");

  const formData = new FormData();
  formData.append("image", fileInput.files[0]);

  try {
    const res = await fetch("/import_menu", {
      method: "POST",
      body: formData
    });

    const data = await res.json();

    if (!res.ok) {
      document.getElementById("response").innerText =
        data.message || "Failed to upload image.";
      return;
    }

    document.getElementById("response").innerText =
      data.message || "Image menu added successfully.";
  } catch (error) {
    document.getElementById("response").innerText = "Error uploading image.";
    console.error(error);
  }
}

// -------------------- ASK QUESTION --------------------
async function askQuestion() {
  const question = document.getElementById("question").value.trim();
  if (!question) return alert("Please enter a question");

  document.getElementById("response").innerText = "Thinking...";

  try {
    const res = await fetch("/ask_menu", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question })
    });

    const data = await res.json();

    if (!res.ok) {
      document.getElementById("response").innerText =
        data.message || "Failed to get answer.";
      return;
    }

    let displayText = data.answer || "No answer found.";
    if (data.verification) {
      displayText += `\n\n[Verification] ${data.verification}`;
    }

    document.getElementById("response").innerText = displayText;
  } catch (error) {
    document.getElementById("response").innerText = "Error asking question.";
    console.error(error);
  }
}
