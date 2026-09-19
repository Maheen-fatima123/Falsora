# Falsora Decision Engine: Complete Integration Summary

This document serves as a complete, layman-friendly guide to everything involving the **Decision Engine** (Mehreen's code) — how it works, what it does, how we adapted it, and how it connects to the rest of the Falsora platform.

---

## 1. What was Mehreen's Code and What Does it Do?

Before we merged everything together, Mehreen wrote a Python backend service to handle the "business logic" and "decision making" for the platform. We took her logic and packaged it into a standalone service called the **Decision Engine**.

Think of the system like a restaurant:
* **The Express API (The Waiter):** Takes your order (the image), talks to the kitchen, and writes the final receipt (the database).
* **The AI Engine (The Chef):** Does the heavy lifting of looking at the pixels and saying "this looks 99% fake."
* **Mehreen's Decision Engine (The Manager):** Looks at the Chef's score, looks at the metadata (like camera type), checks the rulebook, and makes the final executive decision.

Her code has 4 specific, super-important jobs:
1. **The Trust Score Calculator (`/trust-score`)**: Instead of just relying blindly on the AI, her code takes the AI score, checks if the image's metadata indicates it was edited in Photoshop, and checks if we've seen the image before. It uses math to weigh all of these together to give a final percentage score and risk level.
2. **The Live Stream Score (`/trust-score/rolling`)**: When a user is verifying their identity via a live webcam, her code calculates an "exponentially-weighted rolling average". This prevents a user from failing a check just because their camera glitched for a split second, but catches them if they are consistently using a deepfake filter over several seconds.
3. **The State Machine Bouncer (`/case-status/validate`)**: Her code strictly enforces the legal steps of an investigation. If a bug or a hacker tries to illegally change a case from `Verified` back to `Analyzing`, her code blocks it.
4. **The Notification Formatter (`/notifications/format`)**: When a case is flagged, her code takes the raw data and turns it into the professional, human-readable alert messages that get sent to the dashboard.

---

## 2. What Did We Change in Her Code?

We actually did a major architectural change to her code to make it compatible with Falsora.

When she handed it over, her Python script was acting as a monolithic application—meaning her mathematical algorithms and rule checks were heavily tied to a direct connection with a local SQLite database. However, in our system, the Node.js API (using Prisma and Postgres on Neon) is the *only* thing allowed to touch the database to ensure data doesn't get corrupted or out-of-sync.

Here is exactly how we adapted her code:
* **Ripped out the Database Connection:** We completely removed all of her SQLite database connection strings, SQL queries, and ORM code.
* **Preserved her Math & Logic:** We perfectly preserved her actual "brain" algorithms—the logic for the trust engine math, the state machine rules, and the notifications template formatter.
* **Wrapped it in a Web Server:** We took her pure logic functions and wrapped them inside a brand new **FastAPI** microservice.
* **Created HTTP Endpoints:** Instead of her code looking into a database for information, we created API routes (like `POST /trust-score`). Now, the Node.js API packages up the information, sends it over the network to her FastAPI server, her code does the math, and sends the answer back to Node.js!

---

## 3. How We Integrated the Decision Engine

We set up Mehreen’s Python API as a **stateless calculator**.
* **The "Why":** If the Node.js API and the Python API were both allowed to read and write directly to the database at the same time, they would step on each other's toes and corrupt the data. So instead, we made Python "stateless" (meaning it has no database access).
* **How it works:** When someone uploads an image, the Node API saves it to the database. It then sends an HTTP request over to the Python API asking for a score. The Python API runs its algorithms, returns a Trust Score (e.g., 99.2%), and the Node API takes that score and safely updates the database.

---

## 4. How Does it Verify Things Without the AI Engine?

We have not built the `ai-engine` yet (the computer vision/deepfake detection model). Right now, the AI part is just a placeholder. When the Express API calls her Decision Engine, we are currently passing a hardcoded `forgery_score` of `0.0` (meaning "the AI thinks it's perfectly real").

However, Mehreen's algorithm doesn't *just* look at the AI score. It also looks at the metadata! Even without the AI, her code is successfully verifying things using the **EXIF Data** and **Fingerprinting** that we built into the Node API:

* **The Software Flag:** When you upload an image, the Node API reads the hidden metadata (EXIF). If it sees that the image was saved using Photoshop, Canva, or Lightroom, it passes a `software_detected` flag to Mehreen's code. Her code immediately penalizes the trust score and drops the final verdict to **Flagged**, even if the AI score is 0.
* **The Missing Data Flag:** If social media stripped all the metadata out, the Node API passes a `missing_exif` flag. Her code marks it as **Uncertain** or **Flagged** because it can't guarantee where the image came from.
* **The Duplicate Match:** If the exact same image is uploaded twice, the Node API catches the hash match and passes a `fingerprint_match` flag to her code, automatically flagging it as a duplicate.

If you upload a perfectly clean, untouched photo straight from a digital camera, her code sees no bad flags, sees the 0.0 AI score, gives it a 95% Trust Score, and marks it as **Verified**! Once we build the actual `ai-engine`, we will simply replace that hardcoded 0.0 with the real model's score, and her decision engine will instantly become fully functional without needing to change any of her logic.

---

## 5. How We Fixed the "Stuck" AI Processing UX

Real AI models are heavy and take time to process. Before, the backend was either trying to do everything instantly, or it was completely ignoring the final answer and leaving the status as `"Analyzing"` forever. Because the frontend didn't know what was happening, it felt broken to the user.

* **How we fixed it (Backend):** We added a simulated **4.5-second background delay** to the Node API. When you upload an image, it immediately tells the frontend "Got it, I'm analyzing." Then it silently waits for 4.5 seconds in the background before talking to the Python API and locking in the final results (`Flagged` or `Verified`). This perfectly mimics how a heavy, real-world AI pipeline acts.
* **How we fixed it (Frontend):** While that 4.5 seconds is ticking down in the backend, the frontend needed to show the user that something is happening. We added the **scanning laser line** and a **progress bar** (climbing from 0% to 95%). We also added **live polling**—every 2.5 seconds, the frontend silently asks the database if it's done yet. The exact second the backend finishes, the frontend automatically drops the loading screens and reveals the final AI scorecard without you needing to refresh the page!
