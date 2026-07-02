// src/pages/ExploreInsights.js
import React, { useState, useEffect } from 'react';
import { Box, Typography, Card, CardHeader, CardContent, CircularProgress, Alert } from '@mui/material';
import { DataGrid } from '@mui/x-data-grid';
import getApiUrl from '../apiConfig';

const fetchAllInsights = async () => {
  const response = await fetch(`${getApiUrl()}/api/insights`);
  if (!response.ok) {
    throw new Error('Failed to fetch insights from the API.');
  }
  const data = await response.json();
  return data;
};

const updateInsight = async (id, updates) => {
  const response = await fetch(`${getApiUrl()}/api/insights/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
  if (!response.ok) {
    throw new Error('Failed to save changes.');
  }
  return response.json();
};

export default function ExploreInsights() {
  const [insights, setInsights] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [saveError, setSaveError] = useState(null);

  useEffect(() => {
    const loadInsights = async () => {
      try {
        const data = await fetchAllInsights();
        setInsights(data.map((insight, index) => ({
          id: insight.id || index,
          tracked: false,
          notes: '',
          ...insight,
        })));
        setIsLoading(false);
      } catch (err) {
        setError(err.message);
        setIsLoading(false);
      }
    };
    loadInsights();
  }, []);

  const processRowUpdate = async (newRow, oldRow) => {
    const updates = {};
    if (newRow.tracked !== oldRow.tracked) updates.tracked = newRow.tracked;
    if (newRow.notes !== oldRow.notes) updates.notes = newRow.notes;

    if (Object.keys(updates).length === 0) {
      return oldRow;
    }

    await updateInsight(newRow.id, updates);
    setSaveError(null);
    return newRow;
  };

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
    { field: 'tracked', headerName: 'Tracked', type: 'boolean', flex: 0.6, editable: true },
    { field: 'notes', headerName: 'Notes', flex: 2, editable: true },
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
        <CardHeader title="All Discovered Insights" subheader="Browse and search through all your historical insights. Track insights and jot notes directly in the grid." />
        <CardContent>
          {saveError && <Alert severity="error" sx={{ mb: 2 }}>{saveError}</Alert>}
          <div style={{ height: 500, width: '100%' }}>
            <DataGrid
              rows={insights}
              columns={columns}
              pageSize={5}
              rowsPerPageOptions={[5]}
              checkboxSelection
              processRowUpdate={processRowUpdate}
              onProcessRowUpdateError={(err) => setSaveError(err.message)}
            />
          </div>
        </CardContent>
      </Card>
    </Box>
  );
}
