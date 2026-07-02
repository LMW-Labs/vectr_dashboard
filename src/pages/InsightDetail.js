// src/pages/InsightDetail.js
import React, { useState, useEffect } from 'react';
import { useParams, Link as RouterLink } from 'react-router-dom';
import {
  Box, Card, CardHeader, CardContent, Typography, Chip, List, ListItem,
  ListItemText, CircularProgress, Alert, Link,
} from '@mui/material';
import getApiUrl from '../apiConfig';

export default function InsightDetail() {
  const { id } = useParams();
  const [insight, setInsight] = useState(null);
  const [similarInsights, setSimilarInsights] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    // TODO: there's no GET /api/insights/:id endpoint yet, so this fetches
    // the full list and finds the match client-side. Swap for a dedicated
    // endpoint once one exists — cheaper than shipping every insight.
    const loadInsight = async () => {
      try {
        const response = await fetch(`${getApiUrl()}/api/insights`);
        if (!response.ok) {
          throw new Error('Failed to fetch insight.');
        }
        const data = await response.json();
        const match = data.find((item) => item.id === id);
        if (!match) {
          throw new Error('Insight not found.');
        }
        setInsight(match);
      } catch (err) {
        setError(err.message);
      } finally {
        setIsLoading(false);
      }
    };

    // TODO: /api/insights/:id/similar doesn't exist on the backend yet — this
    // wires the fetch for when find_similar_insights() is exposed as an endpoint.
    const loadSimilarInsights = async () => {
      try {
        const response = await fetch(`${getApiUrl()}/api/insights/${id}/similar`);
        if (!response.ok) {
          return;
        }
        const data = await response.json();
        setSimilarInsights(data);
      } catch (err) {
        // Non-fatal: similar insights are a nice-to-have.
      }
    };

    loadInsight();
    loadSimilarInsights();
  }, [id]);

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

  if (!insight) {
    return <Alert severity="warning">Insight not found.</Alert>;
  }

  return (
    <Box>
      <Card sx={{ mb: 3 }}>
        <CardHeader title={insight.insight} subheader={insight.category} />
        <CardContent>
          <Typography variant="body1" sx={{ mb: 2 }}>&ldquo;{insight.quote}&rdquo;</Typography>
          <Chip label={insight.source_type} size="small" sx={{ mr: 1 }} />
          <Chip label={insight.analysis_goal} size="small" sx={{ mr: 1 }} />
          {insight.prompt_version && (
            <Chip label={`prompt v${insight.prompt_version}`} size="small" />
          )}
          <Typography variant="body2" sx={{ mt: 2 }}>
            Source: <Link href={insight.source_url}>{insight.source_url}</Link>
          </Typography>
        </CardContent>
      </Card>

      <Card>
        <CardHeader title="Similar Insights" />
        <CardContent>
          {similarInsights.length === 0 ? (
            <Typography color="text.secondary">No similar insights found yet.</Typography>
          ) : (
            <List>
              {similarInsights.map((item) => (
                <ListItem key={item.id} component={RouterLink} to={`/insights/${item.id}`}>
                  <ListItemText primary={item.insight} secondary={item.quote} />
                </ListItem>
              ))}
            </List>
          )}
        </CardContent>
      </Card>
    </Box>
  );
}
