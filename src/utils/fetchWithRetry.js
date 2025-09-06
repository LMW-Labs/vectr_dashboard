
const fetchWithRetry = async (url, options, retries = 5, backoff = 1000) => {
  for (let i = 0; i < retries; i++) {
    try {
      const response = await fetch(url, options);
      if (!response.ok) {
        // Only retry on specific server errors
        if (response.status >= 500 && response.status <= 599) {
          throw new Error(`Server error: ${response.status}`);
        }
        // For client errors, don't retry, just throw
        const errorData = await response.json().catch(() => ({ error: 'An unknown error occurred.' }));
        throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
      }
      return response;
    } catch (error) {
      if (i < retries - 1) {
        console.log(`Attempt ${i + 1} failed for ${url}. Retrying in ${backoff}ms...`);
        await new Promise(res => setTimeout(res, backoff));
        backoff *= 2; // Exponential backoff
      } else {
        console.error(`All attempts to fetch ${url} failed.`);
        throw error;
      }
    }
  }
};

export default fetchWithRetry;
