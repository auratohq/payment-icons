import hashlib
from io import BytesIO
import unittest

from PIL import Image, ImageDraw

from collection import check_entry, check_image, spreadsheet_safe


def specimen(shape='rounded', hole=False):
    im = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)
    if shape == 'rounded':
        draw.rounded_rectangle((0, 0, 255, 255), radius=43, fill='white')
    elif shape == 'square':
        draw.rectangle((0, 0, 255, 255), fill='white')
    elif shape == 'circle':
        draw.ellipse((0, 0, 255, 255), fill='white')
    if hole:
        draw.rectangle((90, 90, 120, 120), fill=(0, 0, 0, 0))
    stream = BytesIO()
    im.save(stream, format='PNG')
    data = stream.getvalue()
    return data, {'id': 'pmt_test', 'name': 'Test', 'category': 'payment-methods',
                  'path': 'payment-methods/pmt_test.png', 'width': 256, 'height': 256,
                  'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                  'source': {'kind': 'generated', 'url': None}}


class ValidationTests(unittest.TestCase):
    def test_rounded_square_is_accepted(self):
        data, item = specimen()
        check_entry(item)
        check_image(data, item)

    def test_square_and_circle_are_rejected(self):
        for shape in ('square', 'circle'):
            with self.subTest(shape=shape), self.assertRaises(ValueError):
                check_image(*specimen(shape))

    def test_transparent_interior_is_rejected(self):
        with self.assertRaises(ValueError):
            check_image(*specimen(hole=True))

    def test_tampered_bytes_are_rejected(self):
        data, item = specimen()
        with self.assertRaises(ValueError):
            check_image(data + b'changed', item)

    def test_path_traversal_and_hidden_layers_are_rejected(self):
        _, item = specimen()
        for path in ('../outside.png', 'payment-methods/../outside.png', '/payment-methods/pmt_test.png',
                     'payment-methods//pmt_test.png', 'v1/payment-methods/pmt_test.png'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                check_entry({**item, 'path': path})

    def test_source_url_cannot_execute_script(self):
        _, item = specimen()
        item['source']['url'] = 'javascript:alert(1)'
        with self.assertRaises(ValueError):
            check_entry(item)

    def test_csv_formula_is_escaped(self):
        self.assertEqual(spreadsheet_safe('=1+1'), "'=1+1")
        self.assertEqual(spreadsheet_safe('Visa'), 'Visa')


if __name__ == '__main__':
    unittest.main()
