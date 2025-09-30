PROFILES_DATA = {
    "Profile_Snapshot": {
        "name": "SnapShot",
        "vsc_token": "imaging_source_config",
        "vsc_source_token": "imaging",
        "vec_token": "snapshot_enc_config1",
        "encoding": "JPEG",
        "snapshot_profile": True
    }
}

ENCODER_OPTIONS_DATA = {
    "snapshot_enc_config1": """
        <trt:Options token="Profile_Snapshot">
                <tt:QualityRange>
                <tt:Min>0</tt:Min>
                <tt:Max>10</tt:Max>
            </tt:QualityRange>
            <tt:JPEG>
                <tt:ResolutionsAvailable>
                    <tt:Width>{image_width}</tt:Width>
                    <tt:Height>{image_height}</tt:Height>
                </tt:ResolutionsAvailable>
            </tt:JPEG>
            <tt:GuaranteedFrameRateSupported>false</tt:GuaranteedFrameRateSupported> 
        </trt:Options>
    """
}
