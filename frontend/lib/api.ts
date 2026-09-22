export async function fetchApi(url: string, options: RequestInit = {}): Promise<Response> {
  // Ensure credentials are included by default to send cookies
  const fetchOptions: RequestInit = {
    ...options,
    credentials: options.credentials || "include",
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  };

  let response = await fetch(url, fetchOptions);

  // If unauthorized, attempt to refresh token
  if (response.status === 401) {
    try {
      const refreshRes = await fetch("http://localhost:4000/api/auth/refresh", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
      });

      if (refreshRes.ok) {
        // Retry the original request
        response = await fetch(url, fetchOptions);
      } else {
        // Refresh failed, redirect to login (if in browser)
        if (typeof window !== "undefined") {
          window.location.href = "/login";
        }
      }
    } catch (error) {
      console.error("Failed to refresh token:", error);
      if (typeof window !== "undefined") {
        window.location.href = "/login";
      }
    }
  }

  return response;
}
