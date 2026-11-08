const express = require('express');
const app = express();

app.get('/health', (req, res) => res.json({ ok: true }));
app.post('/webhooks/payment', (req, res) => res.sendStatus(204));

module.exports = app;
