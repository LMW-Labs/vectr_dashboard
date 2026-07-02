// src/pages/ExploreInsights.js
import React, { useState, useEffect, useMemo } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { Box, Card, CardHeader, CardContent, CircularProgress, Alert, Chip, Stack, TextField, Link } from '@mui/material';
import { DataGrid, GridToolbar } from '@mui/x-data-grid';
import getApiUrl from '../apiConfig'; // Import the base URL

const fetchAllInsights = async () => {
  const response = await fetch(`${getApiUrl()}/api/insights`); // Use the base URL
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

const toDate = (timestamp) => {
  if (!timestamp) return null;
  if (timestamp._seconds) return new Date(timestamp._seconds * 1000);
  if (timestamp.seconds) return new Date(timestamp.seconds * 1000);
  const parsed = new Date(timestamp);
  return isNaN(parsed.getTime()) ? null : parsed;
};

export default function ExploreInsights() {
  const [insights, setInsights] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [saveError, setSaveError] = useState(null);

  const [categoryFilter, setCategoryFilter] = useState(null);
  const [goalFilter, setGoalFilter] = useState(null);
  const [sourceTypeFilter, setSourceTypeFilter] = useState(null);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

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

  const categories = useMemo(() => [...new Set(insights.map((i) => i.category).filter(Boolean))], [insights]);
  const goals = useMemo(() => [...new Set(insights.map((i) => i.analysis_goal).filter(Boolean))], [insights]);
  const sourceTypes = useMemo(() => [...new Set(insights.map((i) => i.source_type).filter(Boolean))], [insights]);

  const filteredInsights = useMemo(() => {
    return insights.filter((insight) => {
      if (categoryFilter && insight.category !== categoryFilter) return false;
      if (goalFilter && insight.analysis_goal !== goalFilter) return false;
      if (sourceTypeFilter && insight.source_type !== sourceTypeFilter) return false;
      const date = toDate(insight.timestamp);
      if (dateFrom && (!date || date < new Date(dateFrom))) return false;
      if (dateTo && (!date || date > new Date(`${dateTo}T23:59:59`))) return false;
      return true;
    });
  }, [insights, categoryFilter, goalFilter, sourceTypeFilter, dateFrom, dateTo]);

  const processRowUpdate = async (newRow, oldRow) => {
    const updates = {};
    if (newRow.tracked !== oldRow.tracked) updates.tracked = newRow.tracked;
    if (newRow.notes !== oldRow.notes) updates.notes = newRow.notes;

    if (Object.keys(updates).length === 0) {
      return oldRow;
    }

    await updateInsight(newRow.id, updates);
    setSaveError(null);
    setInsights((prev) => prev.map((row) => (row.id === newRow.id ? { ...row, ...updates } : row)));
    return newRow;
  };

  const columns = [
    {
      field: 'insight',
      headerName: 'Insight',
      flex: 2,
      renderCell: (params) => (
        <Link component={RouterLink} to={`/insights/${params.row.id}`}>
          {params.value}
        </Link>
      ),
    },
    { field: 'category', headerName: 'Category', flex: 1 },
    { field: 'analysis_goal', headerName: 'Goal', flex: 1 },
    { field: 'source_type', headerName: 'Source Type', flex: 1 },
    { field: 'source_url', headerName: 'Source URL', flex: 2 },
    {
      field: 'timestamp',
      headerName: 'Date Found',
      type: 'date',
      flex: 1,
      valueGetter: (value) => toDate(value),
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
        <CardHeader title="All Discovered Insights" subheader="Browse and search through all your historical insights." />
        <CardContent>
          {saveError && <Alert severity="error" sx={{ mb: 2 }}>{saveError}</Alert>}
          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 2 }}>
            {categories.map((category) => (
              <Chip
                key={`category-${category}`}
                label={category}
                color={categoryFilter === category ? 'primary' : 'default'}
                onClick={() => setCategoryFilter(categoryFilter === category ? null : category)}
              />
            ))}
            {goals.map((goal) => (
              <Chip
                key={`goal-${goal}`}
                label={goal}
                variant="outlined"
                color={goalFilter === goal ? 'primary' : 'default'}
                onClick={() => setGoalFilter(goalFilter === goal ? null : goal)}
              />
            ))}
            {sourceTypes.map((sourceType) => (
              <Chip
                key={`source-${sourceType}`}
                label={sourceType}
                variant="outlined"
                color={sourceTypeFilter === sourceType ? 'secondary' : 'default'}
                onClick={() => setSourceTypeFilter(sourceTypeFilter === sourceType ? null : sourceType)}
              />
            ))}
            <TextField
              label="From"
              type="date"
              size="small"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              slotProps={{ inputLabel: { shrink: true } }}
            />
            <TextField
              label="To"
              type="date"
              size="small"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              slotProps={{ inputLabel: { shrink: true } }}
            />
          </Stack>
          <div style={{ height: 500, width: '100%' }}>
            <DataGrid
              rows={filteredInsights}
              columns={columns}
              slots={{ toolbar: GridToolbar }}
              initialState={{ pagination: { paginationModel: { pageSize: 10 } } }}
              pageSizeOptions={[10, 25, 50]}
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
