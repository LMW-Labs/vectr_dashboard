import React, { useState } from 'react';
import { Box, TextField, Button, Typography, Grid, CircularProgress, Alert } from '@mui/material';

export default function DiscoverSources() {
  const [query, setQuery] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [results, setResults] = useState([]);
  const [error, setError] = useState(null);

  const handleSearch = async () => {
    setIsLoading(true);
    setError(null);
    setResults([]);

    try {
      const response = await fetch('http://127.0.0.1:5001/api/discover', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ query }),
      });

      if (!response.ok) {
        throw new Error('Failed to fetch from discovery API.');
      }

      const data = await response.json();
      setResults(data.urls);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        Discover New Sources
      </Typography>
      <Typography variant="body1" paragraph>
        Search for websites, articles, or social media content to use in your analysis.
      </Typography>

      <Grid container spacing={2} sx={{ mb: 4 }}>
        <Grid item xs={12} md={9}>
          <TextField
            fullWidth
            label="Search Query (e.g., 'new AI startups')"
            variant="outlined"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </Grid>
        <Grid item xs={12} md={3}>
          <Button
            variant="contained"
            color="primary"
            fullWidth
            onClick={handleSearch}
            sx={{ height: '56px' }}
            disabled={isLoading}
          >
            {isLoading ? <CircularProgress size={24} color="inherit" /> : 'Search'}
          </Button>
        </Grid>
      </Grid>

      {error && <Alert severity="error">{error}</Alert>}

      {results.length > 0 && (
        <Box mt={4}>
          <Typography variant="h6" gutterBottom>
            Search Results
          </Typography>
          <ul>
            {results.map((url, index) => (
              <li key={index}>
                <a href={url} target="_blank" rel="noopener noreferrer">{url}</a>
              </li>
            ))}
          </ul>
        </Box>
      )}
    </Box>
  );
}