$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$taskScript = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'voice-demo.json') -Raw | ConvertFrom-Json
$taskVoice = New-Object -ComObject SAPI.SpVoice
$taskVoices = $taskVoice.GetVoices()
for ($taskIndex = 0; $taskIndex -lt $taskScript.en.Count; $taskIndex++) {
    $taskLine = $taskScript.en[$taskIndex]
    for ($taskVoiceIndex = 0; $taskVoiceIndex -lt $taskVoices.Count; $taskVoiceIndex++) {
        $taskToken = $taskVoices.Item($taskVoiceIndex)
        $taskName = if ($taskLine.speaker -eq 'plumo') { 'David' } else { 'Zira' }
        if ($taskToken.GetDescription().Contains($taskName)) { $taskVoice.Voice = $taskToken; break }
    }
    $taskStream = New-Object -ComObject SAPI.SpFileStream
    $taskStream.Format.Type = 22
    $taskStream.Open((Join-Path $taskRoot "work/voice-demo/en-$taskIndex.wav"), 3, $false)
    $taskVoice.AudioOutputStream = $taskStream
    $taskVoice.Rate = 0
    $null = $taskVoice.Speak($taskLine.text)
    $taskStream.Close()
}
