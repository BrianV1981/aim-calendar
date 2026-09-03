import unittest
import os
import tempfile

def parse_sms_xml(xml_path):
    raise NotImplementedError("TDD: Needs implementation")

class TestSMSIngest(unittest.TestCase):
    def test_parse_sms_xml(self):
        xml_content = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<smses count="1">
  <sms protocol="0" address="17279454981" date="1672531200000" type="1" subject="null" body="Happy New Year!" toa="null" sc_toa="null" service_center="null" read="1" status="-1" locked="0" date_sent="0" sub_id="1" readable_date="Jan 1, 2023 12:00:00 AM" contact_name="Ariana" />
</smses>"""
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=".xml") as f:
            f.write(xml_content)
            temp_path = f.name
            
        with self.assertRaises(NotImplementedError):
            parse_sms_xml(temp_path)
            
        os.remove(temp_path)

if __name__ == '__main__':
    unittest.main()
