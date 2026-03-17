document.getElementById("add-url-btn").addEventListener("click", addURL);
document.getElementById("add-image-btn").addEventListener("click", addImage);
document.getElementById("ask-btn").addEventListener("click", askQuestion);

// -------------------- ADD MENU FROM URL --------------------
async function addURL() {
  const urlInput = document.getElementById("menu-url");
  const url = urlInput.value.trim();

  if (!url) return alert("Please enter a URL");

  setResponse("Importing menu from URL...");

  try {
    const res = await fetch("/import_menu", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url })
    });

    const data = await res.json();

    if (!res.ok) {
      return setResponse(data.message || "Failed to import menu.");
    }

    setResponse(`✅ Menu added\nItems: ${data.items}`);
    urlInput.value = "";

  } catch (err) {
    console.error(err);
    setResponse("Error importing menu.");
  }
}

// -------------------- ADD MENU FROM IMAGE --------------------
async function addImage() {
  const fileInput = document.getElementById("menu-image");

  if (!fileInput.files.length) {
    return alert("Please select an image");
  }

  setResponse("Processing image...");

  const formData = new FormData();
  formData.append("image", fileInput.files[0]);

  try {
    const res = await fetch("/import_menu", {
      method: "POST",
      body: formData
    });

    const data = await res.json();

    if (!res.ok) {
      return setResponse(data.message || "Upload failed.");
    }

    setResponse("Image menu added successfully");
    fileInput.value = "";

  } catch (err) {
    console.error(err);
    setResponse("Error uploading image.");
  }
}

// -------------------- ASK QUESTION --------------------
async function askQuestion() {
  const textarea = document.getElementById("question");
  const question = textarea.value.trim();

  if (!question) return alert("Please enter a question");

  setResponse("Thinking... 🤔");

  try {
    const res = await fetch("/ask_menu", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question })
    });

    const data = await res.json();

    if (!res.ok) {
      return setResponse(data.message || "Failed to get answer.");
    }

    let output = data.answer;

    if (data.verification) {
      output += `\n\n[Verification: ${data.verification}]`;
    }

    setResponse(output);
    textarea.value = "";

  } catch (err) {
    console.error(err);
    setResponse("Error asking question.");
  }
}

// -------------------- HELPER --------------------
function setResponse(text) {
  document.getElementById("response").innerText = text;
}
