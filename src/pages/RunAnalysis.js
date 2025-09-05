// src/pages/RunAnalysis.js

import React, { useState, useEffect } from 'react';
import {
  Box, Card, CardContent, CardHeader, TextField, Button, 
  Select, MenuItem, FormControl, InputLabel, Typography, 
  CircularProgress, Grid, Alert, FormGroup, FormControlLabel, Checkbox
} from '@mui/material';
import { DataGrid } from '@mui/x-data-grid';
import API_BASE_URL from '../apiConfig';

const goalOptions = [
    { label: '--- Marketing & Sales ---', value: 'header1', disabled: true },
    { label: 'Find Lead Generation Needs', value: 'lead_generation' },
    { label: 'Identify CAC Reduction Pain', value: 'cac_reduction' },
    { label: 'Track Brand Awareness Goals', value: 'brand_awareness' },
    { label: 'Discover Market Expansion Plans', value: 'market_expansion' },
    {label: '--- Operations & Efficiency ---', value: 'header2', disabled: true},
    {label: 'Find Workflow Automation Needs', value: 'workflow_automation'},
    {label: 'Identify Hiring & Talent Gaps', value: 'hiring_talent'},
    {label: 'Discover Supply Chain Issues', value: 'supply_chain'},
    {label: '--- Customer-Centric ---', value: 'header3', disabled: true},
    {label: 'Find Customer Retention Goals', value: 'customer_retention'},
    {label: 'Identify Customer Support Challenges', value: 'customer_support'},
    {label: 'Find User Feedback Requests', value: 'user_feedback'},
    {label: 'Analyze Executive Subtext', value: 'executive_subtext'},
];

export default function RunAnalysis() {
  const [goal, setGoal] = useState('lead_generation');
  const [sites, setSites] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [results, setResults] = useState(null);
  const [error, setError] = useState('');
  const [discoveredSources, setDiscoveredSources] = useState([]);
  const [selectedSources, setSelectedSources] = useState({});

  useEffect(() => {
    const fetchDiscoveredSources = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/discovered_sources`);
        if (!response.ok) {
          throw new Error('Could not fetch discovered sources.');
        }
        const data = await response.json();
        setDiscoveredSources(data);
      } catch (err) {
        console.error("Error fetching sources:", err);
      }
    };
    fetchDiscoveredSources();
  }, []);

  const handleCheckboxChange = (event) => {
    setSelectedSources({
      ...selectedSources,
      [event.target.name]: event.target.checked,
    });
  };

  const handleStartAnalysis = async () => {
    setIsLoading(true);
    setError('');
    setResults(null);

    const manualSites = sites.split('\n').filter(site => site.trim() !== '');
    const selectedSites = Object.keys(selectedSources).filter(url => selectedSources[url]);
    const combinedSites = [...new Set([...manualSites, ...selectedSites])];

    if (combinedSites.length === 0) {
        setError("Please enter or select at least one website.");
        setIsLoading(false);
        return;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/api/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          analysisGoal: goal,
          sites: combinedSites.join('\n'),
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
        <CardHeader title="Analysis Criteria" subheader="Select an analysis goal, choose sources, and start your run." />
        <CardContent>
          <Grid container spacing={3}>
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

            {discoveredSources.length > 0 && (
                <Grid item xs={12}>
                    <Typography variant="subtitle1" gutterBottom>Select from Discovered Sources</Typography>
                    <Card variant="outlined" sx={{ maxHeight: 250, overflow: 'auto', p: 2, bgcolor: 'grey.50' }}>
                        <FormGroup>
                            {discoveredSources.map((source) => (
                                <FormControlLabel
                                    key={source.id}
                                    control={
                                        <Checkbox
                                            checked={selectedSources[source.url] || false}
                                            onChange={handleCheckboxChange}
                                            name={source.url}
                                        />
                                    }
                                    label={source.url}
                                />
                            ))}
                        </FormGroup>
                    </Card>
                </Grid>
            )}

            <Grid item xs={12}>
                <TextField
                    fullWidth
                    multiline
                    rows={4}
                    label="Or Manually Add Websites (one per line)"
                    variant="outlined"
                    value={sites}
                    onChange={(e) => setSites(e.target.value)}
                />
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
               <Grid item xs={12} md={5}>
                <Typography variant="h6" align="center" gutterBottom>Common Themes</Typography>
                {results.wordcloud ? (
                  <img src={results.wordcloud} alt="Insight Word Cloud" style={{ width: '100%', borderRadius: '8px' }} />
                ) : (
                  <Typography align="center">No word cloud data available.</Typography>
                )}
              </Grid>
               <Grid item xs={12} md={7} sx={{ minHeight: 400 }}>
                 <Typography variant="h6" align="center" gutterBottom>Discovered Opportunities</Typography>
                 <DataGrid
                    rows={results.data.map((row, index) => ({ id: index, ...row }))}
                    columns={results.columns.map(col => ({ field: col.id, headerName: col.name, flex: 1 }))}
                    initialState={{
                      pagination: { paginationModel: { pageSize: 5 } },
                    }}
                    pageSizeOptions={[5, 10, 20]}
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
