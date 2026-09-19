# Falsora Decision Engine & AI Simulation Integration

This document outlines how we integrated Mehreen's Python Decision Engine into the Falsora platform, and how we built the user experience around it to make it feel like a real AI product.

## 1. How we integrated Mehreen's Backend (Decision Engine)

### The Architecture Choice
We set up Mehreen's Python backend (`decision-engine`) as a **stateless microservice**. 
* **What that means:** It runs completely on its own on a separate port (8001) and does not talk to the database at all. It acts purely like a calculator.
* **Why we chose this:** If both the Node.js API and the Python API tried to write to the database at the same time, they would constantly overwrite each other and cause data corruption. By making Python "stateless", the Node API handles all the database saving, and simply asks the Python API for the math (the Trust Score).

### The Integration Flow
1. **Upload:** A user uploads an image via the Next.js frontend.
2. **Node API:** The Express API receives the image, saves it to the database as `"Analyzing"`, extracts the metadata (EXIF), and calculates the hashes.
3. **Python Call:** The Node API then sends an HTTP request to Mehreen's Python API asking for a score.
4. **Python Math:** The Python API calculates the Trust Score and Risk Level based on her rules and sends the answer back.
5. **Node API Saves:** The Node API takes that answer and updates the database with the final result (`Flagged` or `Verified`).

## 2. How we built the "AI Processing" UX (The New Code)

### The Problem
AI models take time to run. If the user uploads an image and the page just freezes, or if the page shows the final results instantly, it either feels broken or fake. You noticed the UI felt stuck and lacked feedback.

### The Backend Change (Simulating Time)
In the Node.js API (`core-api/src/routes/cases.ts`), we changed the upload code to use a **background worker delay** (`setTimeout`). 
* **What we did:** When an image is uploaded, the backend immediately tells the frontend "I received it, it is now Analyzing." Then, it waits 4.5 seconds in the background before talking to the Decision Engine and finalizing the result.
* **Why we chose this:** This accurately mimics how heavy Machine Learning models behave in the real world. It forces the system to stay in the "Analyzing" state for a few seconds.

### The Frontend Change (Progress Bar & Polling)
In the Next.js frontend (`frontend/app/dashboard/cases/[id]/page.tsx`), we added two main features:
1. **The Visuals:** If the case is `"Analyzing"`, we show a laser scanner animating over the image and a progress bar that slowly counts from 0% to 95%. The final AI scorecards are hidden behind loading skeletons.
2. **Live Polling:** We added a background loop that silently asks the database "Are you done yet?" every 2.5 seconds. 
* **Why we chose this:** The progress bar gives the user peace of mind that the app hasn't frozen. The live polling ensures that the exact second the backend finishes the 4.5-second AI simulation, the frontend automatically drops the loading screens and reveals the final results without the user ever having to hit refresh.
