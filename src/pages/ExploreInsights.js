// src/pages/ExploreInsights.js
import React, { useState, useEffect } from 'react';
import { Box, Typography, Card, CardHeader, CardContent, CircularProgress, Alert } from '@mui/material';
import { DataGrid } from '@mui/x-data-grid';

const fetchAllInsights = async () => {
  const response = await fetch('http://127.0.0.1:5001/api/insights');
  if (!response.ok) {
    throw new Error('Failed to fetch insights from the API.');
  }
  const data = await response.json();
  return data;
};

export default function ExploreInsights() {
  const [insights, setInsights] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const loadInsights = async () => {
      try {
        const data = await fetchAllInsights();
        setInsights(data.map((insight, index) => ({ id: insight.id || index, ...insight })));
        setIsLoading(false);
      } catch (err) {
        setError(err.message);
        setIsLoading(false);
      }
    };
    loadInsights();
  }, []);

  const columns = [
    { field: 'title', headerName: 'Insight', flex: 2 },
    { field: 'analysis_goal', headerName: 'Goal', flex: 1 },
    { field: 'source_url', headerName: 'Source URL', flex: 2 },
    {
      field: 'timestamp',
      headerName: 'Date Found',
      type: 'date',
      flex: 1,
      valueGetter: (params) => {
        if (params.row && params.row.timestamp && params.row.timestamp._seconds) {
          return new Date(params.row.timestamp._seconds * 1000);
        }
        return null;
      },
    },
  ];

  if (isLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return <Alert severity="error">{error}</Alert>;
  }

  return (
    <Box>
      <Card>
        <CardHeader title="All Discovered Insights" subheader="Browse and search through all your historical insights." />
        <CardContent>
          <div style={{ height: 400, width: '100%' }}>
            <DataGrid
              rows={insights}
              columns={columns}
              pageSize={5}
              rowsPerPageOptions={[5]}
              checkboxSelection
            />
          </div>
        </CardContent>
      </Card>
    </Box>
  );
}