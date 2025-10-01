# Onvif Responses
import xml.etree.ElementTree as ET
from datetime import datetime, timezone 

def create_fault_response(fault_string):
    """
    Genera una risposta SOAP Fault standard.
    """
    return f"""
    <soap:Fault>
        <soap:Code>
            <soap:Value>soap:Sender</soap:Value>
            <soap:Subcode>
                <soap:Value>wsse:FailedAuthentication</soap:Value>
            </soap:Subcode>
        </soap:Code>
        <soap:Reason>
            <soap:Text xml:lang="en">{fault_string}</soap:Text>
        </soap:Reason>
    </soap:Fault>
    """

def get_capabilities_response(announce_ip, server_port):
    return f"""
            <tds:GetCapabilitiesResponse xmlns:tds="http://www.onvif.org/ver10/device/wsdl">
                <tds:Capabilities>
                    <tt:Device xmlns:tt="http://www.onvif.org/ver10/schema">
                        <tt:XAddr>http://{announce_ip}:{server_port}/onvif/device_service</tt:XAddr>
                    </tt:Device>
                    <tt:Media xmlns:tt="http://www.onvif.org/ver10/schema">
                        <tt:XAddr>http://{announce_ip}:{server_port}/onvif/media_service</tt:XAddr>
                        <tt:StreamingCapabilities>
                            <tt:RTPMulticast>false</tt:RTPMulticast>
                            <tt:RTP_TCP>true</tt:RTP_TCP>
                            <tt:RTP_RTSP_TCP>true</tt:RTP_RTSP_TCP>
                        </tt:StreamingCapabilities>
                    </tt:Media>
                </tds:Capabilities>
            </tds:GetCapabilitiesResponse>
            """


def get_hostname_response():
    return f"""
            <tds:GetHostnameResponse xmlns:tds="http://www.onvif.org/ver10/device/wsdl">
                <tt:HostnameInformation xmlns:tt="http://www.onvif.org/ver10/schema">
                    <tt:FromDHCP>false</tt:FromDHCP>
                    <tt:Name>zeroCam-onvif</tt:Name>
                </tt:HostnameInformation>
            </tds:GetHostnameResponse>
            """


def get_device_information_response():
    return f"""
            <tds:GetDeviceInformationResponse xmlns:tds="http://www.onvif.org/ver10/device/wsdl">
                <tt:Manufacturer xmlns:tt="http://www.onvif.org/ver10/schema">zeroCam</tt:Manufacturer>
                <tt:Model>zeroCam-Pi</tt:Model>
                <tt:FirmwareVersion>1.0.0</tt:FirmwareVersion>
                <tt:SerialNumber>ZC001</tt:SerialNumber>
                <tt:HardwareId>raspberry-pi</tt:HardwareId>
            </tds:GetDeviceInformationResponse>
            """

def get_system_date_and_time_response(now):
    return f"""
            <tds:GetSystemDateAndTimeResponse xmlns:tds="http://www.onvif.org/ver10/device/wsdl">
                <tds:SystemDateAndTime>
                    <tt:DateTimeType xmlns:tt="http://www.onvif.org/ver10/schema">Manual</tt:DateTimeType> 
                    <tt:DaylightSavings xmlns:tt="http://www.onvif.org/ver10/schema">false</tt:DaylightSavings>
                    <tt:TimeZone xmlns:tt="http://www.onvif.org/ver10/schema">
                        <tt:TZ>Etc/GMT</tt:TZ>
                    </tt:TimeZone>
                    <tt:UTCDateTime xmlns:tt="http://www.onvif.org/ver10/schema">
                        <tt:Time>
                            <tt:Hour>{now.hour}</tt:Hour>
                            <tt:Minute>{now.minute}</tt:Minute>
                            <tt:Second>{now.second}</tt:Second>
                        </tt:Time>
                        <tt:Date>
                            <tt:Year>{now.year}</tt:Year>
                            <tt:Month>{now.month}</tt:Month>
                            <tt:Day>{now.day}</tt:Day>
                        </tt:Date>
                    </tt:UTCDateTime>
                </tds:SystemDateAndTime>
            </tds:GetSystemDateAndTimeResponse>
            """

def get_dns_response():
    return f"""
            <tds:GetDNSResponse xmlns:tds="http://www.onvif.org/ver10/device/wsdl">
                <tds:DNSInformation>
                    <tt:FromDHCP xmlns:tt="http://www.onvif.org/ver10/schema">false</tt:FromDHCP>
                </tds:DNSInformation>
            </tds:GetDNSResponse>
            """

def get_network_interfaces_response(announce_ip):
    return f"""
            <tds:GetNetworkInterfacesResponse xmlns:tds="http://www.onvif.org/ver10/device/wsdl">
                <tds:NetworkInterfaces token="eth0_token">
                    <tt:Enabled xmlns:tt="http://www.onvif.org/ver10/schema">true</tt:Enabled>
                    <tt:Info xmlns:tt="http://www.onvif.org/ver10/schema">
                        <tt:Name>eth0</tt:Name>
                        <tt:HwAddress>00:11:22:33:44:55</tt:HwAddress>
                        <tt:MTU>1500</tt:MTU>
                    </tt:Info>
                    <tt:IPv4 xmlns:tt="http://www.onvif.org/ver10/schema">
                        <tt:Enabled>true</tt:Enabled>
                        <tt:Config>
                            <tt:Manual>
                                <tt:Address>{announce_ip}</tt:Address>
                                <tt:PrefixLength>24</tt:PrefixLength>
                            </tt:Manual>
                        </tt:Config>
                    </tt:IPv4>
                </tds:NetworkInterfaces>
            </tds:GetNetworkInterfacesResponse>
            """

def get_scopes_response():
    return f"""
            <tds:GetScopesResponse xmlns:tds="http://www.onvif.org/ver10/device/wsdl" 
                                 xmlns:tt="http://www.onvif.org/ver10/schema">
                <tds:Scopes>
                    <tt:ScopeDef>Fixed</tt:ScopeDef>
                    <tt:ScopeItem>onvif://www.onvif.org/type/NetworkVideoTransmitter</tt:ScopeItem>
                    <tt:ScopeItem>onvif://www.onvif.org/hardware/zeroCam-Pi</tt:ScopeItem>
                    <tt:ScopeItem>onvif://www.onvif.org/name/zeroCam</tt:ScopeItem>
                </tds:Scopes>
            </tds:GetScopesResponse>
            """

def get_profiles_response(profiles_data, image_width, image_height):
    profiles_xml = ""
    for token, data in profiles_data.items():
        profiles_xml += f"""
            <trt:Profiles token="{token}" fixed="true" xmlns:tt="http://www.onvif.org/ver10/schema">
                <tt:Name>{data['name']}</tt:Name>
                <tt:VideoSourceConfiguration token="{data['vsc_token']}">
                    <tt:Name>{data['name']}_VSC</tt:Name>
                    <tt:UseCount>1</tt:UseCount>
                    <tt:SourceToken>{data['vsc_source_token']}</tt:SourceToken>
                    <tt:Bounds x="0" y="0" width="{image_width}" height="{image_height}"/>
                </tt:VideoSourceConfiguration>
                <tt:VideoEncoderConfiguration token="{data['vec_token']}">
                    <tt:Name>{data['name']}_VEC</tt:Name>
                    <tt:UseCount>1</tt:UseCount>
                    <tt:Encoding>{data['encoding']}</tt:Encoding>
                    <tt:Resolution>
                        <tt:Width>{image_width}</tt:Width>
                        <tt:Height>{image_height}</tt:Height>
                    </tt:Resolution>
                    <tt:SessionTimeout>PT60S</tt:SessionTimeout>
                </tt:VideoEncoderConfiguration>
            </trt:Profiles>
        """
    return f"""
        <trt:GetProfilesResponse xmlns:trt="http://www.onvif.org/ver10/media/wsdl">
            {profiles_xml}
        </trt:GetProfilesResponse>
    """

def get_video_sources_response(profiles_data, image_width, image_height):
    videoSourceXml = ""
    # Since we only have one source for all profiles now
    source_token = next(iter(profiles_data.values()))['vsc_source_token']
    
    videoSourceXml += f"""
        <trt:VideoSources token="{source_token}" xmlns:tt="http://www.onvif.org/ver10/schema">
            <tt:Framerate>1</tt:Framerate>
            <tt:Resolution>
                <tt:Width>{image_width}</tt:Width>
                <tt:Height>{image_height}</tt:Height>
            </tt:Resolution>
        </trt:VideoSources>
    """

    return f"""
            <trt:GetVideoSourcesResponse xmlns:trt="http://www.onvif.org/ver10/media/wsdl">
                {videoSourceXml}
            </trt:GetVideoSourcesResponse>
            """
            
def get_video_encoder_configuration_options(encoder_options_data, requested_token, image_width, image_height):
    options_xml_template = encoder_options_data.get(requested_token, "")
    options_xml = options_xml_template.format(image_width=image_width, image_height=image_height)
    response = f"""<trt:GetVideoEncoderConfigurationOptionsResponse xmlns:trt="http://www.onvif.org/ver10/media/wsdl"
                                                              xmlns:tt="http://www.onvif.org/ver10/schema">
                       {options_xml}
                   </trt:GetVideoEncoderConfigurationOptionsResponse>"""
    return response

def get_video_encoder_configurations(profiles_data, image_width, image_height):
    configurations_xml = ""

    for profile_data in profiles_data.values():
        configurations_xml += f"""
            <trt:Configurations token="{profile_data['vec_token']}" xmlns:tt="http://www.onvif.org/ver10/schema">
                <tt:Name>{profile_data['name']}_VEC</tt:Name>
                <tt:UseCount>1</tt:UseCount>
                <tt:Encoding>{profile_data['encoding']}</tt:Encoding>
                <tt:Resolution>
                    <tt:Width>{image_width}</tt:Width>
                    <tt:Height>{image_height}</tt:Height>
                </tt:Resolution>
                <tt:Quality>10</tt:Quality>
                <tt:SessionTimeout>PT60S</tt:SessionTimeout>
            </trt:Configurations>
        """

    response_body = f"""
    <trt:GetVideoEncoderConfigurationsResponse xmlns:trt="http://www.onvif.org/ver10/media/wsdl">
        {configurations_xml}
    </trt:GetVideoEncoderConfigurationsResponse>
    """
    return response_body


def get_video_encoder_configuration(profiles_data, requested_token, image_width, image_height):
    found_data = next(iter(profiles_data.values()))

    response_body = f"""
    <trt:GetVideoEncoderConfigurationResponse xmlns:trt="http://www.onvif.org/ver10/media/wsdl">
        <trt:Configuration token="{found_data['vec_token']}" xmlns:tt="http://www.onvif.org/ver10/schema">
            <tt:Name>{found_data['name']}_VEC</tt:Name>
            <tt:UseCount>1</tt:UseCount>
            <tt:Encoding>{found_data['encoding']}</tt:Encoding>
            <tt:Resolution>
                <tt:Width>{image_width}</tt:Width>
                <tt:Height>{image_height}</tt:Height>
            </tt:Resolution>
            <tt:Quality>10</tt:Quality>
            <tt:SessionTimeout>PT60S</tt:SessionTimeout>
        </trt:Configuration>
    </trt:GetVideoEncoderConfigurationResponse>
    """
    return response_body


def get_snapshot_uri_response(announce_ip, server_port):
    return f"""
            <trt:GetSnapshotUriResponse xmlns:trt="http://www.onvif.org/ver10/media/wsdl">
                <trt:MediaUri xmlns:tt="http://www.onvif.org/ver10/schema">
                    <tt:Uri>http://{announce_ip}:{server_port}/snapshot.jpg</tt:Uri>
                    <tt:InvalidAfterConnect>false</tt:InvalidAfterConnect>
                    <tt:InvalidAfterReboot>false</tt:InvalidAfterReboot>
                    <tt:Timeout>PT0S</tt:Timeout>
                </trt:MediaUri>
            </trt:GetSnapshotUriResponse>
            """

def handle_get_stream_uri(profiles_data, request_data, announce_ip, rtsp_port, logger):
    return None # No stream URI for snapshot-only profile

def get_profile_response(profiles_data, profile_token, image_width, image_height):
    profile_data = profiles_data.get(profile_token, next(iter(profiles_data.values())))
    
    return f"""
            <trt:GetProfileResponse xmlns:trt="http://www.onvif.org/ver10/media/wsdl">
                <trt:Profile token="{profile_token}" fixed="true" xmlns:tt="http://www.onvif.org/ver10/schema">
                    <tt:Name>{profile_data['name']}</tt:Name>
                    <tt:VideoSourceConfiguration token="{profile_data['vsc_token']}">
                        <tt:Name>{profile_data['name']}_VSC</tt:Name>
                        <tt:UseCount>1</tt:UseCount>
                        <tt:SourceToken>{profile_data['vsc_source_token']}</tt:SourceToken>
                        <tt:Bounds x="0" y="0" width="{image_width}" height="{image_height}"/>
                    </tt:VideoSourceConfiguration>
                    
                    <tt:VideoEncoderConfiguration token="{profile_data['vec_token']}">
                        <tt:Name>{profile_data['name']}_VEC</tt:Name>
                        <tt:UseCount>1</tt:UseCount>
                        <tt:Encoding>{profile_data['encoding']}</tt:Encoding>
                        <tt:Resolution>
                            <tt:Width>{image_width}</tt:Width>
                            <tt:Height>{image_height}</tt:Height>
                        </tt:Resolution>
                        <tt:Quality>5</tt:Quality>
                        <tt:SessionTimeout>PT60S</tt:SessionTimeout>
                    </tt:VideoEncoderConfiguration>
                </trt:Profile>
            </trt:GetProfileResponse>
            """

def get_video_source_configuration_response(requested_config_token, image_width, image_height):
    return f"""
            <trt:GetVideoSourceConfigurationResponse xmlns:trt="http://www.onvif.org/ver10/media/wsdl">
                <trt:Configuration token="{requested_config_token}" xmlns:tt="http://www.onvif.org/ver10/schema">
                    <tt:Name>PrimaryVideoSource</tt:Name> 
                    <tt:UseCount>1</tt:UseCount>
                    <tt:SourceToken>{requested_config_token}</tt:SourceToken>  
                    <tt:Bounds x="0" y="0" width="{image_width}" height="{image_height}"/>
                </trt:Configuration>
            </trt:GetVideoSourceConfigurationResponse>
            """
