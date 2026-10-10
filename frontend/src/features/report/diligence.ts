/** The kinds of diligence that can answer what public sources cannot. */
export const diligence: Record<string, { label: string; how: string }> = {
  proprietary_data: { label: 'Proprietary data', how: 'Ask the company for the data room.' },
  patient_level_data: {
    label: 'Patient-level data',
    how: 'Needs trial data below the published summary.',
  },
  kol_interview: { label: 'Expert interview', how: 'Ask clinicians who ran or compete with it.' },
  experiment: { label: 'Experiment', how: 'Only a new experiment can answer it.' },
  cmc_diligence: { label: 'CMC diligence', how: 'Manufacturing and supply review.' },
  ip_diligence: { label: 'IP diligence', how: 'Patent scope and freedom to operate.' },
}
