const express = require("express");
const path = require("path");

const app = express();
const PORT = 3000;

// Custom route to serve MainMenu.html at the root
app.get("/", (req, res) => {
    res.sendFile(path.join(__dirname, "index.html"));
});

// Serve static files without automatically serving index.html
app.use(express.static(__dirname, { index: false }));

app.listen(PORT, () => {
    console.log(`Server running at http://localhost:${PORT}`);
});

