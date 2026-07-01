// src/pages/ScansPage.js
import React from 'react';
import { Box, Card, CardHeader, CardContent, Typography } from '@mui/material';

// TODO: build out scheduled scan management here — list/create/edit/enable
// docs in the Firestore 'scans' collection that scheduled_scan.py reads.
export default function ScansPage() {
  return (
    <Box>
      <Card>
        <CardHeader title="Scheduled Scans" subheader="Manage recurring analysis runs." />
        <CardContent>
          <Typography color="text.secondary">
            Scheduled scan management is coming soon.
          </Typography>
        </CardContent>
      </Card>
    </Box>
  );
}
