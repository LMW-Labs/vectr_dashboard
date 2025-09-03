// src/pages/RunAnalysis.js

import React, { useState } from 'react';
import { Box, Card, CardContent, CardHeader, TextField, Button, Select, MenuItem, FormControl, InputLabel, Typography, CircularProgress, Grid, Alert } from '@mui/material';
import { DataGrid } from '@mui/x-data-grid'; // A powerful data table component from MUI

// These options are taken directly from your original Dash app
const goalOptions = [
    { label: '--- Marketing & Sales ---', value: 'header1', disabled: true },
    { label: 'Find Lead Generation Needs', value: 'lead_generation' },
    { label: 'Identify CAC Reduction Pain', value: 'cac_reduction' },
    { label: 'Track Brand Awareness Goals', value: 'brand_awareness' },
    { label: 'Discover Market Expansion Plans', value: 'market_expansion' },
    // Add the rest of your goal options here...
];

export default function RunAnalysis() {
  // State management for the form and results
  const [apiKey, setApiKey] = useState('');
  const [goal, setGoal] = useState('lead_generation');
  const [sites, setSites] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [results, setResults] = useState(null);
  const [error, setError] = useState('');

  const handleStartAnalysis = async () => {
    setIsLoading(true);
    setError('');
    setResults(null);

    try {
      const response = await fetch('http://127.0.0.1:5001/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          apiKey: apiKey,
          analysisGoal: goal,
          sites: sites,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || 'An unknown error occurred.');
      }
      
      setResults(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Box>
      <Card sx={{ mb: 4 }}>
        <CardHeader title="Analysis Criteria" subheader="Enter details below to start a new analysis run." />
        <CardContent>
          <Grid container spacing={2}>
            <Grid item xs={12}>
              <TextField fullWidth type="password" label="Gemini API Key" variant="outlined" value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
            </Grid>
            <Grid item xs={12}>
              <FormControl fullWidth>
                <InputLabel>Analysis Goal</InputLabel>
                <Select value={goal} label="Analysis Goal" onChange={(e) => setGoal(e.target.value)}>
                  {goalOptions.map((opt) => (
                    <MenuItem key={opt.value} value={opt.value} disabled={opt.disabled}>
                      {opt.label}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12}>
              <TextField fullWidth multiline rows={6} label="Target Websites (one per line)" variant="outlined" value={sites} onChange={(e) => setSites(e.target.value)} />
            </Grid>
            <Grid item xs={12}>
              <Button variant="contained" size="large" fullWidth onClick={handleStartAnalysis} disabled={isLoading}>
                {isLoading ? <CircularProgress size={24} color="inherit" /> : 'Start Analysis'}
              </Button>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {error && <Alert severity="error" sx={{ mb: 4 }}>{error}</Alert>}

      {results && (
        <Card>
          <CardHeader title="Analysis Results" />
          <CardContent>
            <Grid container spacing={3}>
              <Grid item xs={12} lg={5}>
                <Typography variant="h6" align="center" gutterBottom>Common Themes</Typography>
                {results.wordcloud ? (
                  <img src={results.wordcloud} alt="Insight Word Cloud" style={{ width: '100%', borderRadius: '8px' }} />
                ) : (
                  <Typography align="center">No word cloud data available.</Typography>
                )}
              </Grid>
              <Grid item xs={12} lg={7} style={{ minHeight: 400, width: '100%' }}>
                 <Typography variant="h6" align="center" gutterBottom>Discovered Opportunities</Typography>
                 <DataGrid
                    rows={results.data.map((row, index) => ({ id: index, ...row }))} // DataGrid requires a unique 'id' for each row
                    columns={results.columns.map(col => ({ field: col.id, headerName: col.name, flex: 1 }))}
                    pageSize={5}
                    rowsPerPageOptions={[5]}
                    autoHeight
                 />
              </Grid>
            </Grid>
          </CardContent>
        </Card>
      )}
    </Box>
  );
}