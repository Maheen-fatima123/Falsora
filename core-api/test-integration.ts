import fs from "fs";
import path from "path";

const CORE_API_URL = "http://localhost:4000/api";
let jwtCookie = "";
let testCaseId = "";

async function runTests() {
  console.log("🦋 Starting Integration Tests...\n");

  try {
    // 1. Login to get a token
    console.log("1️⃣ Logging in as administrator...");
    const loginRes = await fetch(`${CORE_API_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: "admin@falsora.ai", password: "admin123" }), // Use your actual seed creds
    });
    
    if (!loginRes.ok) throw new Error("Login failed. Have you seeded the database?");
    
    // Extract the JWT cookie
    const setCookie = loginRes.headers.get("set-cookie");
    if (setCookie) {
      jwtCookie = setCookie.split(";")[0]!;
    }
    console.log("   ✅ Logged in successfully.\n");

    // 2. Test Analytics Dashboard
    console.log("2️⃣ Testing Analytics Dashboard...");
    const analyticsRes = await fetch(`${CORE_API_URL}/analytics/dashboard`, {
      headers: { Cookie: jwtCookie },
    });
    const analyticsData = await analyticsRes.json();
    if (analyticsData.success) {
      console.log("   ✅ Analytics fetched:", JSON.stringify(analyticsData.data, null, 2));
    } else {
      console.error("   ❌ Analytics failed:", analyticsData);
    }
    console.log();

    // 3. Test Invalid Status Transition
    // We need an existing case ID. Let's try to fetch cases first.
    console.log("3️⃣ Fetching cases to test status transitions...");
    const casesRes = await fetch(`${CORE_API_URL}/cases`, {
      headers: { Cookie: jwtCookie },
    });
    const casesData = await casesRes.json();
    
    if (casesData.success && casesData.data.length > 0) {
      testCaseId = casesData.data[0].id;
      console.log(`   Found case: ${testCaseId}. Current status: ${casesData.data[0].status}`);

      // Try an invalid transition (e.g., whatever status it is -> Verified -> Analyzing)
      console.log("   Attempting to force an invalid transition (Verified -> Analyzing)...");
      
      // First force it to Verified (assuming it's Analyzing or Flagged)
      await fetch(`${CORE_API_URL}/cases/${testCaseId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", Cookie: jwtCookie },
        body: JSON.stringify({ status: "Verified" }),
      });

      // Now try to go BACK to Analyzing (which should fail according to orchestration rules)
      const badTransitionRes = await fetch(`${CORE_API_URL}/cases/${testCaseId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", Cookie: jwtCookie },
        body: JSON.stringify({ status: "Analyzing" }),
      });

      const badTransitionData = await badTransitionRes.json();
      if (!badTransitionRes.ok && !badTransitionData.success) {
        console.log("   ✅ Correctly blocked invalid transition!");
        console.log("      Error from server:", badTransitionData.message);
      } else {
        console.error("   ❌ Failed to block invalid transition!", badTransitionData);
      }
    } else {
      console.log("   ⚠️ No cases found in the database. Upload an image in the UI first to test transitions.");
    }

    console.log("\n🎉 Tests complete!");
    console.log("\nTo test the Trust Score specifically, upload an image via the Frontend UI while both core-api and decision-engine are running, and check if the risk level is populated.");

  } catch (err) {
    console.error("\n❌ Test script failed:", err);
  }
}

runTests();
